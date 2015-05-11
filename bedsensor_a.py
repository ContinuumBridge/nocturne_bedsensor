#!/usr/bin/env python
# bedsensor_a.py
# Copyright (C) ContinuumBridge Limited, 2015 - All Rights Reserved
# Written by Peter Claydon
#

import sys
import time
from cbcommslib import CbAdaptor
from cbconfig import *
from btle import Peripheral
import struct
from twisted.internet import threads
from twisted.internet import reactor
from twisted.internet import task

class Adaptor(CbAdaptor):
    def __init__(self, argv):
        self.status =           "ok"
        self.state =            "stopped"
        self.apps =             {"binary_sensor": []}
        self.minInterval =      1000
        # super's __init__ must be called:
        #super(Adaptor, self).__init__(argv)
        CbAdaptor.__init__(self, argv)

    def setState(self, action):
        # error is only ever set from the running state, so set back to running if error is cleared
        if action == "error":
            self.state == "error"
        elif action == "clear_error":
            self.state = "running"
        msg = {"id": self.id,
               "status": "state",
               "state": self.state}
        self.sendManagerMessage(msg)

    def sendCharacteristic(self, characteristic, data, timeStamp):
        msg = {"id": self.id,
               "content": "characteristic",
               "characteristic": characteristic,
               "data": data,
               "timeStamp": timeStamp}
        for a in self.apps[characteristic]:
            self.sendMessage(msg, a)

    def poll(self):
        c = struct.unpack('<b', self.sensor.readCharacteristic(0x24))[0]
        #self.cbLog("debug", "poll, c: " + str(c))
        if c == 1:
            b = "on"
        else:
            b = "off"
        self.sendCharacteristic("binary_sensor", b, time.time())

    def initSensor(self):
        self.sensor = Peripheral(self.addr)
        self.cbLog("debug", "initSensor, initialised")
        t = task.LoopingCall(self.poll)
        t.start(3.0)

    def onAppInit(self, message):
        resp = {"name": self.name,
                "id": self.id,
                "status": "ok",
                "service": [{"characteristic": "binary_sensor",
                             "interval": 3.0}],
                "content": "service"}
        self.sendMessage(resp, message["id"])
        self.setState("running")
        
    def onAppRequest(self, message):
        #self.cbLog("debug", "onAppRequest: " + str(message))
        # Switch off anything that already exists for this app
        for a in self.apps:
            if message["id"] in self.apps[a]:
                self.apps[a].remove(message["id"])
        # Now update details based on the message
        for f in message["service"]:
            if message["id"] not in self.apps[f["characteristic"]]:
                self.apps[f["characteristic"]].append(message["id"])
                if f["interval"] < self.minInterval:
                    self.minInterval = f["interval"]
        self.cbLog("debug", "onAppRequest, apps: " + str(self.apps))

    def onAppCommand(self, message):
        if "data" not in message:
            self.cbLog("warning", "app message without data: " + str(message))
        else:
            self.cbLog("warning", "This is a sensor. Message not understood: " +  str(message))

    def onConfigureMessage(self, config):
        """Config is based on what apps are to be connected.
            May be called again if there is a new configuration, which
            could be because a new app has been added.
        """
        reactor.callInThread(self.initSensor)
        self.setState("starting")

if __name__ == '__main__':
    adaptor = Adaptor(sys.argv)
