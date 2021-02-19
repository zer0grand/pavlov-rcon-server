import asyncio
import json
import websockets
import time
from threading import Event, Thread

from pavlov import PavlovRCON

refreshTime = 3;
bufferTime = .1;

players = { }
commandQueue = [ ]

users = set()
serverInfo = { }

async def execute_next_command():
    while True:
        if len(commandQueue) > 0:
            command = commandQueue.pop(0)
            print("execute: "+ command)
            await rcon.send(command)
        await asyncio.sleep(bufferTime)
        
def get_rcon_server():
    with open("credentials.json", "r") as cred:
        data = json.load(cred)
        ip = data["ip"]
        port = data["port"]
        password = data["password"]
        return PavlovRCON(ip, port, password)

async def ws_server(websocket, path):
    global rcon
    await register(websocket)
    try:
        async for message in websocket:
            print(message)
            rconData = await rcon.send(message)
            print(rconData)
            await websocket.send(json.dumps(rconData))
    finally:
        await unregister(websocket)

def interpret_message(s):
    message = json.Parse(s)
    for command in message["commands"]:
        for playerId in message["players"]:
            commandQueue.push(prefix +" "+ playerId +" "+ suffix)
        

async def register(websocket):
    users.add(websocket)
    print("registered")
    print(websocket.remote_address)
    sendMessage = {
        "type": "init",
        "data": {
            "ServerInfo": serverInfo,
            "Players": players
        }
    }
    await websocket.send(json.dumps(sendMessage))

async def unregister(websocket):
    users.remove(websocket)
    print("unregistered")

async def send_to_all_users(message):
    for user in users:
        await user.send(json.dumps(message))

async def refresh_player_list():
    global players
    global serverInfo
    while True:
##        print("tick")
        newPlayerList = { }
        newServerInfo = await rcon.send("ServerInfo")
        newServerInfo = newServerInfo["ServerInfo"]
        if (newServerInfo != serverInfo):
            serverInfo = newServerInfo
            await server_updated()
        
        playerList = await rcon.send("RefreshList")

        for player in playerList["PlayerList"]:
            uid = player["UniqueId"]
            newPlayerList[uid] = {"PlayerName": player["Username"]}
        for playerId in newPlayerList.keys():
            playerDetails = await rcon.send("InspectPlayer "+ playerId)
            newPlayerList[playerId] = playerDetails["PlayerInfo"]

        for playerId in players.keys():
            if playerId in newPlayerList and players[playerId] != newPlayerList[playerId]:
                await player_updated(playerId)

        
        playersSet = set(players.keys())
        newPlayersSet = set(newPlayerList.keys())
        left = playersSet.difference(newPlayersSet)
        joined = newPlayersSet.difference(playersSet)
        players = {**players, **newPlayerList}
        for player in left:
            players.pop(player)
            await player_left(player)
        for player in joined:
            await player_joined(player)
                
        await asyncio.sleep(refreshTime)

async def player_joined(playerId):
    print(playerId +" joined")
    players[playerId]["JoinedAt"] = int(time.time())
    message = {
        "type": "player-join",
        "data": players[playerId]
    }
    await send_to_all_users(message)

async def player_updated(playerId):
##    print(playerId +" updated")
    message = {
        "type": "player-update",
        "data": players[playerId]
    }
    await send_to_all_users(message)
    
async def player_left(playerId):
    print(playerId +" left")
    message = {
        "type": "player-leave",
        "data": {
            "UniqueId": playerId
        }
    }
    await send_to_all_users(message)

async def server_updated():
    message = {
        "type": "server-update",
        "data": serverInfo
    }
    await send_to_all_users(message)

rcon = get_rcon_server()

commandQueueLoop = asyncio.ensure_future(execute_next_command())
serverRefreshLoop = asyncio.ensure_future(refresh_player_list())

start_server = websockets.serve(ws_server, "localhost", 7285)

asyncio.get_event_loop().run_until_complete(start_server)
asyncio.get_event_loop().run_forever()
