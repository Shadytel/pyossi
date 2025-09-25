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

Fieldset.add_fieldset(Fieldset("udp", [
    Field("extncodes", "0fa2ff00", 5),
    Field("extncode", "0fa3ff02", 5),
    Field("type_default", "0fa4ff02", 7),
    Field("enpcode_default", "0fa5ff02", 3),
    Field("udpcode_default", "0fa6ff02", 3),
    # Generate fields for all 100 line suffixes (00-99)
    *[Field(f"type_{i:02d}", f"0fa4ff{i+14:02x}", 7) for i in range(100)],
    *[Field(f"enpcode_{i:02d}", f"0fa5ff{i+14:02x}", 3) for i in range(100)],
    *[Field(f"udpcode_{i:02d}", f"0fa6ff{i+14:02x}", 3) for i in range(100)]
]))

Fieldset.add_fieldset(Fieldset("configuration", [
    Field("boardnum", "0001ff00", 11),
    Field("boardtype", "0002ff00", 20),
    Field("code", "0003ff00", 6),
    Field("suf1", "0004ff00", 1),
    Field("suf2", "6800ff00", 1),
    Field("vintage", "0005ff00", 10),
    # Slots?
    *[Field(f"slot_{i+1:02d}", f"{i+6:04x}ff00", 2) for i in range(24)],
    *[Field(f"slot_{i+25:02d}", f"{i+0x07d1:04x}ff00", 2) for i in range(8)],
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
    RELEASE = "release"
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
    UDP = "udp"
    CONFIGURATION = "configuration"

class OSSIException(Exception):
    def __init__(self, msg, cmd):
        self._msg = msg
        self._cmd = cmd

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
        exception = None
        while True:
            line = self._proc.stdout.readline().strip()
            # print(line)
            if line[0] == 'c':
                result['cmd'] = line[1:]
            elif line[0] == 'f':
                result_fields_names.append(line[1:].split("\t"))
            elif line[0] == 'd':
                result_fields_values.append(line[1:].split("\t"))
            elif line[0] == 'n' or line[0] == 't':
                # OSSI has a weird quirk in that the line number of the fields
                # and values matters. If values are unset for the rest of the
                # corresponding line, it will omit them. Thus, we have to do
                # this silly little dance.
                row_field_values = []
                for (field_names, field_values) in list(zip(result_fields_names, result_fields_values)):
                    row_field_values.extend(list(zip(field_names, field_values)))
                result["rows"].append(row_field_values)
                result_fields_values = []
                if line[0] == 't':
                    if exception:
                        raise exception
                    return result
            elif line[0] == 'e':
                exception = OSSIException(line[1:], cmd)

    def get(self, verb, noun, identifier=None, fields=None):
        cmd = self._verb_noun_to_cmd(verb, noun, identifier)
        if fields:
            hex_fields = map(noun.get_field_hex_from_name, fields)
            raw_res = self._send_raw_query(cmd, hex_fields)
        else:
            raw_res = self._send_raw_query(cmd)
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
        hex_fields = map(noun.get_field_hex_from_name, field_name)
        raw_res = self._send_raw_query(cmd, hex_fields, field_value)
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
