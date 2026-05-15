"""
서바이벌 게임 WebSocket 릴레이 서버 (최대 8인).
Render.com 무료 티어 배포용.

배포 방법:
  1. GitHub 새 레포에 server.py + requirements.txt 업로드
  2. Render.com → New Web Service → 레포 연결
  3. Start Command: python server.py
  4. 배포 후 URL을 netplay.py의 SERVER_URL 에 입력
"""
import asyncio
import json
import os
import random

try:
    import websockets
    from websockets.exceptions import ConnectionClosed
except ImportError:
    raise SystemExit("pip install websockets")

_rooms: dict = {}   # code -> {'host': ws, 'guests': list[ws]}
_CODE_CHARS = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'
_MAX_GUESTS = 7     # 호스트 1 + 게스트 최대 7 = 최대 8인


def _gen_code() -> str:
    for _ in range(200):
        code = ''.join(random.choices(_CODE_CHARS, k=4))
        if code not in _rooms:
            return code
    return 'XXXX'


async def _try_send(ws, data: dict):
    if ws is None:
        return
    try:
        await ws.send(json.dumps(data, ensure_ascii=False, separators=(',', ':')))
    except Exception:
        pass


async def _send_all(wss, data: dict):
    for ws in list(wss):
        await _try_send(ws, data)


async def _handler(ws):
    my_code: str | None = None
    my_role: str | None = None   # 'host' | 'guest'
    my_slot: int = 0             # 0=호스트, 1-7=게스트

    try:
        async for raw in ws:
            try:
                msg = json.loads(raw)
            except Exception:
                continue
            t = msg.get('type')

            # ── 방 만들기 ──────────────────────────────────────
            if t == 'create':
                code = _gen_code()
                _rooms[code] = {'host': ws, 'guests': []}
                my_code = code
                my_role = 'host'
                my_slot = 0
                await _try_send(ws, {'type': 'created', 'code': code})

            # ── 방 입장 ────────────────────────────────────────
            elif t == 'join':
                code = msg.get('code', '').strip().upper()
                if code in _rooms and len(_rooms[code]['guests']) < _MAX_GUESTS:
                    room  = _rooms[code]
                    slot  = len(room['guests']) + 1   # 슬롯 1-7
                    room['guests'].append(ws)
                    my_code = code
                    my_role = 'guest'
                    my_slot = slot
                    count   = 1 + len(room['guests'])
                    await _try_send(ws, {
                        'type': 'joined', 'code': code, 'slot': slot, 'count': count
                    })
                    await _try_send(room['host'], {
                        'type': 'guest_joined', 'slot': slot, 'count': count,
                        'char': msg.get('char', 0)
                    })
                elif code not in _rooms:
                    await _try_send(ws, {'type': 'error', 'msg': 'invalid_code'})
                else:
                    await _try_send(ws, {'type': 'error', 'msg': 'room_full'})

            # ── 메시지 릴레이 ──────────────────────────────────
            elif my_code and my_code in _rooms:
                room = _rooms[my_code]
                if my_role == 'host':
                    # 호스트 → 모든 게스트에게
                    await _send_all(room['guests'], msg)
                else:
                    # 게스트 → 호스트에게 (슬롯 번호 첨부)
                    msg['slot'] = my_slot
                    await _try_send(room['host'], msg)

    except (ConnectionClosed, Exception):
        pass
    finally:
        if my_code and my_code in _rooms:
            room = _rooms[my_code]
            if my_role == 'host':
                # 호스트 종료 → 방 삭제, 모든 게스트에게 알림
                await _send_all(room['guests'], {'type': 'disconnect'})
                del _rooms[my_code]
            else:
                # 게스트 종료 → 목록에서 제거, 호스트에게 알림
                if ws in room['guests']:
                    room['guests'].remove(ws)
                await _try_send(room['host'], {'type': 'guest_left', 'slot': my_slot})
        print(f'[연결 해제] {my_code} (슬롯 {my_slot})')


async def main():
    port = int(os.environ.get('PORT', 8765))
    print(f'[서버] 포트 {port} 에서 대기 중 (최대 8인)...')
    async with websockets.serve(_handler, '0.0.0.0', port):
        await asyncio.Future()


asyncio.run(main())
