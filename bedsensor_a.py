#!/usr/bin/env python
# bedsensor_a.py
# Copyright (C) ContinuumBridge Limited, 2015 - All Rights Reserved
# Written by Peter Claydon
#

import sys
import time
import pexpect
from cbcommslib import CbAdaptor
from cbconfig import *
from twisted.internet import threads
from twisted.internet import reactor
from twisted.internet import task

INIT_TIMEOUT = 16         # Timeout when initialising SensorTag (sec)
GATT_SLEEP_TIME = 2       # Time to sleep between killing one gatt process & starting another
POLL_INTERVAL = 3         # How often to poll sensor

class Adaptor(CbAdaptor):
    def __init__(self, argv):
        self.status =           "ok"
        self.state =            "stopped"
        self.apps =             {
            "binary_sensor": [],
            "connected": []
        }
        self.minInterval =      1000
        self.connected = False
        # super's __init__ must be called:
        #super(Adaptor, self).__init__(argv)
        CbAdaptor.__init__(self, argv)

    def setState(self, action):
        # error is only ever set from the running state, so set back to running if error is cleared
        if action == "error":
            self.state == "error"
        elif action == "clear_error":
            self.state = "running"
        else:
            self.state = action
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

    def threadLog(self, level,log):
        reactor.callFromThread(self.cbLog, level, log)

    def initSensorTag(self):
        self.threadLog("info", "Init")
        try:
            cmd = 'gatttool -i ' + self.device + ' -b ' + self.addr + \
                  ' --interactive'
            self.threadLog("debug", "cmd: " + str(cmd))
            self.gatt = pexpect.spawn(cmd)
        except:
            self.threadLog("error", "Dead!")
            self.connected = False
            self.threadLog("debug", "initSensorTag 1, connected: " + str(self.connected))
            reactor.callFromThread(self.sendCharacteristic, "connected", self.connected, time.time())
            return "noConnect"
        self.gatt.expect('\[LE\]>')
        self.gatt.sendline('connect')
        index = self.gatt.expect(['successful', pexpect.TIMEOUT, pexpect.EOF], timeout=INIT_TIMEOUT)
        if index == 1 or index == 2:
            # index 2 is not actually a timeout, but something has gone wrong
            self.connected = False
            self.threadLog("debug", "initSensorTag 2, connected: " + str(self.connected))
            reactor.callFromThread(self.sendCharacteristic, "connected", self.connected, time.time())
            self.gatt.kill(9)
            # Wait a second just to give SensorTag time to "recover"
            time.sleep(1)
            return "timeout"
        else:
            self.connected = True
            self.threadLog("debug", "initSensorTag 3, connected: " + str(self.connected))
            reactor.callFromThread(self.sendCharacteristic, "connected", self.connected, time.time())
            return "ok"

    def poll(self):
        self.initSensorTag()
        while not self.doStop:
            try:
                line = 'char-read-hnd 0x24'
                self.gatt.sendline(line)
                index = self.gatt.expect(['Characteristic value/descriptor:.*', pexpect.TIMEOUT, pexpect.EOF], timeout=POLL_INTERVAL)
                if index == 1 or index == 2:
                    status = ""
                    self.threadLog("warning", "gatt timeout")
                    # First try to reconnect nicely
                    self.gatt.sendline('connect')
                    index = self.gatt.expect(['successful', pexpect.TIMEOUT, pexpect.EOF], timeout=INIT_TIMEOUT)
                    if index == 1 or index == 2:
                        self.gatt.kill(9)
                        time.sleep(GATT_SLEEP_TIME)
                        status = self.initSensorTag()   
                        self.threadLog("info", "re-init status: " + status)
                    else:
                        self.threadLog("debug", "Successful reconnection without kill")
                else:
                    raw = self.gatt.after.split()
                    c = raw[2]
                    #self.threadLog("debug", "poll. raw[2]: " + str(raw[2]))
                    if c == "01":
                        b = "on"
                    else:
                        b = "off"
                    reactor.callFromThread(self.sendCharacteristic, "binary_sensor", b, time.time())
            except Exception as ex:
                self.threadLog("warning", "problem polling device. Type: " + str(type(ex)) + ", exception: " +  str(ex.args))
            time.sleep(POLL_INTERVAL)
        try:
            self.gatt.sendline(disconnect)
        except Exception as ex:
            self.threadLog("warning", "poll, unclean exit. Type: " + str(type(ex)) + ", exception: " +  str(ex.args))

    def initSensor(self):
        self.cbLog("debug", "initSensor, initialising")
        reactor.callInThread(self.poll)

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
        self.initSensor()
        self.setState("starting")

if __name__ == '__main__':
    adaptor = Adaptor(sys.argv)
