#!/usr/bin/env python3

import subprocess
import json
import pprint

from enum import Enum

class Field:
    def __init__(self, name, hex, length):
        self._name = name
        self._hex = hex
        self._length = length

class Fieldset:
    fieldsets = {}

    def __init__(self, noun, fields):
        self._noun = noun
        self._fields = fields

        self._field_name_to_hex = {}
        self._field_hex_to_name = {}

        for field in self._fields:
            self._field_name_to_hex[field._name] = field._hex
            self._field_hex_to_name[field._hex] = field._name

    def get_field_hex_from_name(self, name):
        if name in self._field_name_to_hex:
            return self._field_name_to_hex[name]
        else:
            raise Exception(f"Field name \"{name}\" unknown for {self._noun} fieldset")

    def get_field_name_from_hex(self, hex):
        # Default to the hex value if it's unknown
        return self._field_hex_to_name.get(hex, hex)

    def add_fieldset(fieldset):
        Fieldset.fieldsets[fieldset._noun] = fieldset

    def get_fieldset(noun):
        return Fieldset.fieldsets[noun]
    
Fieldset.add_fieldset(Fieldset("station", [
    Field("extn", "8005ff00", 5),
    Field("port", "8004ff00", 7),
    Field("name", "8003ff00", 27),
    Field("tn", "4a3bff00", 3),
    Field("cor", "8001ff00", 2),
    Field("cos", "8002ff00", 2),
    Field("dataextn", "0019ff00", 5),
    Field("dataname", "001cff00", 27),
    Field("datacos", "8020ff00", 2),
    Field("datacor", "8021ff00", 2),
    Field("datatn", "4a3cff00", 3),
]))

# add
# busyout
# change
# display
# erase
# get vector
# list
# test

class Verb(Enum):
    def __init__(self, name):
        self._name = name
    
    ADD = "add"
    BUSYOUT = "busyout"
    CHANGE = "change"
    DISPLAY = "display"
    ERASE = "erase"
    GET = "get"
    LIST = "list"
    TEST = "test"

class Noun(Enum):
    def __init__(self, name):
        self._name = name
        self._fieldset = Fieldset.get_fieldset(name)
    
    def get_field_hex_from_name(self, name):
        return self._fieldset.get_field_hex_from_name(name)
    
    def get_field_name_from_hex(self, hex):
        return self._fieldset.get_field_name_from_hex(hex)
    
    STATION = "station"
    
class OSSI:        
    def connect(self):
        # This is gross and should probably be rewritten
        self._proc = subprocess.Popen(
            ["ssh", "-tt", "isdn-modem-c"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            text=True
            )
        # Eat the ISR's "Password OK"
        self._proc.stdout.readline()
        self._proc.stdout.readline()

    def _verb_noun_to_cmd(self, verb, noun, identifier):
        cmd = f"{verb._name} {noun._name}"
        if identifier:
            cmd += f" {identifier}"
        return cmd
    
    def _send_raw_query(self, cmd, fields=None, data=None):
        raw_cmd = f"c{cmd}\n"
        if fields:
            raw_cmd += "f"
            for param in fields:
                raw_cmd += f"{param}\t"
            raw_cmd += "\n"
        if data:
            raw_cmd += "d"
            for d in data:
                raw_cmd += f"{d}\t"
            raw_cmd += "\n"
        raw_cmd += "t\n"
        # print(raw_cmd)
        self._proc.stdin.write(raw_cmd)
        self._proc.stdin.flush()
        result = { "rows": [] }
        result_fields_names = []
        result_fields_values = []
        while True:
            line = self._proc.stdout.readline().strip()
            # print(line)
            if line[0] == 'c':
                result['cmd'] = line[1:]
            elif line[0] == 'f':
                result_fields_names.extend(line[1:].split("\t"))
            elif line[0] == 'd':
                result_fields_values.extend(line[1:].split("\t"))
            elif line[0] == 'n':
                # print(result_fields_names)
                # print(result_fields_values)
                result["rows"].append(list(zip(result_fields_names, result_fields_values)))
                result_fields_values = []
            elif line[0] == 'e':
                raise Exception(line[1:])
            elif line[0] == 't':
                return result

    def get(self, verb, noun, identifier=None, fields=None):
        hex_fields = map(noun.get_field_hex_from_name, fields)
        cmd = self._verb_noun_to_cmd(verb, noun, identifier)
        raw_res = self._send_raw_query(cmd, hex_fields)
        res = { 'cmd': raw_res['cmd'], 'rows': [] }
        for row in raw_res['rows']:
            fields = {}
            for field in row:
                fields[noun.get_field_name_from_hex(field[0])] = field[1]
            res['rows'].append(fields)
        return res

    def put(self, verb, noun, identifier=None, data=None):
        field_name, field_value = tuple([list(t) for t in zip(*data)])
        cmd = self._verb_noun_to_cmd(verb, noun, identifier)
        raw_res = self._send_raw_query(cmd, hex_fields)
        res = { 'cmd': raw_res['cmd'], 'rows': [] }
        for row in raw_res['rows']:
            fields = {}
            for field in row:
                fields[noun.get_field_name_from_hex(field[0])] = field[1]
            res['rows'].append(fields)
        return res

def main():
    ossi = OSSI()
    ossi.connect()
    pprint.pp(ossi.get(Verb.LIST, Noun.STATION, fields=["extn", "name"]))

if __name__ == '__main__':
    main()