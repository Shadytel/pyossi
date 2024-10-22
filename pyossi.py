#!/usr/bin/env python3

import subprocess
import json

class Field:
    def __init__(self, name, hex):
        self._name = name
        self._hex = hex

class OSSI:        
    def connect(self):
        # This is gross and should probably be rewritten
        self._proc = subprocess.Popen(
            ["ssh", "-tt", "isdn-modem-c"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            text=True
            )
        self._proc.stdout.readline()
        self._proc.stdout.readline()

    def _send_query(self, cmd, params=None):
        raw_cmd = f"c{cmd}\n"
        if params:
            raw_cmd += "f"
            for param in params:
                raw_cmd += f"{param}\t"
            raw_cmd += "\n"
        raw_cmd += "t\n"
        print(raw_cmd)
        self._proc.stdin.write(raw_cmd)
        self._proc.stdin.flush()
        result = { "entries": [] }
        result_params_names = []
        result_params_values = []
        while True:
            line = self._proc.stdout.readline().strip()
            print(line)
            if line[0] == 'c':
                result['cmd'] = line[1:]
            elif line[0] == 'f':
                result_params_names.extend(line[1:].split("\t"))
            elif line[0] == 'd':
                result_params_values.extend(line[1:].split("\t"))
            elif line[0] == 'n':
                print(result_params_names)
                print(result_params_values)
                result["entries"].append(list(zip(result_params_names, result_params_values)))
                result_params_values = []
            elif line[0] == 't':
                return result

def main():
    ossi = OSSI()
    ossi.connect()
    print(ossi._send_query("list sta", ["8005ff00", "8003ff00", "8004ff00"]))

main()
