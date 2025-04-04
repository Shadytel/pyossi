#!/usr/bin/env python3

import argparse
import asyncio
import queue
import threading

from aiohttp import web
from ossi import *

class OSSIThread:
    def __init__(self):
        self._queue = queue.Queue()
        pass

    def run(self):
        threading.Thread(target=self._worker, daemon=True).start()

    def _worker(self):
        ossi = OSSI()
        ossi.connect()
        print("Connected to OSSI!")

        while True:
            cmd = self._queue.get()
            try:
                cmd._response = cmd.run(ossi)
            except OSSIException as e:
                cmd._exception = e
            with cmd._cv:
                cmd._cv.notify()
            self._queue.task_done()

    def _execute_blocking(self, cmd):
        self._queue.put(cmd)
        with cmd._cv:
            cmd._cv.wait()

    async def execute(self, cmd):
        await asyncio.to_thread(self._execute_blocking, cmd)
        if cmd._exception:
            raise cmd._exception
        else:
            return cmd._response

class OSSICommand:
    def __init__(self, verb, noun, identifier=None):
        self._verb = verb
        self._noun = noun
        self._identifier = identifier
        self._response = None
        self._exception = None
        self._cv = threading.Condition()

class OSSIGetCommand(OSSICommand):
    def __init__(self, verb, noun, identifier=None, fields=None):
        super().__init__(verb, noun, identifier)
        self._fields = fields

    def run(self, ossi):
        return ossi.get(self._verb, self._noun, self._identifier, self._fields)

class OSSIPutCommand(OSSICommand):
    def __init__(self, verb, noun, identifier=None, data=None):
        super().__init__(verb, noun, identifier)
        self._data = data.items()

    def run(self, ossi):
        return ossi.put(self._verb, self._noun, self._identifier, self._data)

class PyOSSIDaemon:
    def __init__(self, **kwargs):
        self._app = web.Application()
        self._ossi_thread = OSSIThread()

        self._app.add_routes([web.get('/api/station', self.list_station)])
        self._app.add_routes([web.get('/api/station/{extn}', self.get_station)])

        self._app.add_routes([web.get('/api/station/{extn}/busyout', self.busyout_station)])
        self._app.add_routes([web.get('/api/station/{extn}/release', self.release_station)])
        self._app.add_routes([web.get('/api/station/{extn}/test', self.test_station)])

        self._app.add_routes([web.post('/api/station/{extn}', self.create_station)])
        self._app.add_routes([web.patch('/api/station/{extn}', self.patch_station)])

        self._app.add_routes([web.delete('/api/station/{extn}', self.delete_station)])

        self._app.add_routes([web.get('/api/udp/{prefix}', self.get_udp)])

    def _process_fields(self, request):
        fields = request.query.getone('fields', None)
        if fields:
            fields = fields.split(',')
        return fields

    async def _try_cmd(self, cmd):
        try:
            resp = await self._ossi_thread.execute(cmd)
            return web.json_response(resp)
        except OSSIException as e:
            raise web.HTTPBadRequest(text=str(e))

    async def list_station(self, request):
        fields = self._process_fields(request)
        cmd = OSSIGetCommand(Verb.LIST, Noun.STATION, fields=fields)
        return await self._try_cmd(cmd)

    async def get_station(self, request):
        extn = request.match_info.get("extn", None)
        fields = self._process_fields(request)
        cmd = OSSIGetCommand(Verb.LIST, Noun.STATION, extn, fields)
        return await self._try_cmd(cmd)

    async def busyout_station(self, request):
        extn = request.match_info.get("extn", None)
        cmd = OSSIGetCommand(Verb.BUSYOUT, Noun.STATION, extn)
        return await self._try_cmd(cmd)

    async def release_station(self, request):
        extn = request.match_info.get("extn", None)
        cmd = OSSIGetCommand(Verb.RELEASE, Noun.STATION, extn)
        return await self._try_cmd(cmd)

    async def test_station(self, request):
        extn = request.match_info.get("extn", None)
        cmd = OSSIGetCommand(Verb.TEST, Noun.STATION, extn)
        return await self._try_cmd(cmd)

    async def create_station(self, request):
        extn = request.match_info.get("extn", None)
        data = await request.post()
        cmd = OSSIPutCommand(Verb.CREATE, Noun.STATION, extn, data)
        return await self._try_cmd(cmd)

    async def patch_station(self, request):
        extn = request.match_info.get("extn", None)
        data = await request.post()
        cmd = OSSIPutCommand(Verb.CHANGE, Noun.STATION, extn, data)
        return await self._try_cmd(cmd)

    async def delete_station(self, request):
        extn = request.match_info.get("extn", None)
        cmd = OSSIPutCommand(Verb.ERASE, Noun.STATION, extn)
        return await self._try_cmd(cmd)
    
    async def get_udp(self, request):
        prefix = request.match_info.get("prefix", None)
        cmd = OSSIGetCommand(Verb.DISPLAY, Noun.UDP, prefix)
        return await self._try_cmd(cmd)

    def run(self, path):
        self._ossi_thread.run()
        web.run_app(self._app, path=path)

# def main():
#     ossi = OSSI()
#     ossi.connect()
#     pprint.pp(ossi._send_raw_query("list sta", fields=["8005ff00", "8003ff00"]))

def main():
    arg_parser = argparse.ArgumentParser(description='Definity API server')
    arg_parser.add_argument('-P', '--port', help='TCP port to serve on.', default='8080')
    arg_parser.add_argument('-U', '--path', help='Unix file system path to serve on.')
    args = arg_parser.parse_args()

    daemon = PyOSSIDaemon(**vars(args))
    daemon.run(args.path)

if __name__ == '__main__':
    main()
