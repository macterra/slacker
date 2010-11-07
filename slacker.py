#!/usr/bin/env python

from ircbot import SingleServerIRCBot
from irclib import nm_to_n, irc_lower, DEBUG
from lwqueue import lwqueue
from xmlrpclib import ServerProxy
from threading import Thread
import string, time, re, random

def wrap(text, width):
    """
    A word-wrap function that preserves existing line breaks
    and most spaces in the text. Expects that existing line
    breaks are posix newlines (\n).
    """
    return reduce(lambda line, word, width=width: '%s%s%s' %
                  (line,
                   ' \n'[(len(line)-line.rfind('\n')-1
                         + len(word.split('\n',1)[0]
                              ) >= width)],
                   word),
                  text.split(' ')
                 )

class AsyncSend(Thread):
    def __init__(self,proxy,chan,msg,bot):
        Thread.__init__(self)
        self.proxy = proxy
        self.channel = chan
        self.msg = msg
        self.bot = bot

    def run(self):
        try:
            self.proxy.llRemoteData({"Channel" : self.channel, "IntValue" : 0, "StringValue" : self.msg})
            print "sending on channel %s: %s" % (self.channel, self.msg)
        except:
            print "llRemoteData failed on channel %s" % (self.channel)
            self.bot.removeChannel(self.channel)
            
class SlackerBot(SingleServerIRCBot):
    def __init__(self, channel, nickname, server, port=6667, queue='test', voiced=False):
        SingleServerIRCBot.__init__(self, [(server, port)], nickname, nickname)
        self.nickname = nickname
        self.channel = channel
        self.SLchannels = {}
        self.queue = 0
        self.queueName = queue
        self.voiced = voiced
        self.verbose = 1
        self.lastName = ""
        self.lastMsg = ""
        
    def initQueue(self):
        self.proxy = ServerProxy("http://xmlrpc.secondlife.com/cgi-bin/xmlrpc.cgi")
        self.queue = lwqueue('127.0.0.1',self.queueName)
        msg = self.queue.pop()
        while msg:
            msg = self.queue.pop()
        
    def check(self):
        if not self.queue:
            print "no queue yet"
            return
        
        packet = self.queue.pop()
        
        while packet:
            name, message, channel, location = packet
            #print "received packet: name=%s messages=%s channel=%s location=%s" % (name, message, channel, location)
            self.SLchannels[channel] = location

            if name == 'topic':
                self.connection.topic(self.channel)
            else:
                if name == self.lastName and message == self.lastMsg:
                    return

                self.lastName = name
                self.lastMsg = message
                
                if message[0:3] == '/me':
                    msg = "[%s] %s %s" % (location, name, message[4:])
                    self.announce(msg)
                    #self.sendSL(msg,channel)
                else:
                    wrapped = wrap(message,80)
                    lines = wrapped.split('\n')
                    for line in lines:
                        msg = "[%s] %s: %s" % (location, name, line)
                        self.announce(msg)
                        #self.sendSL(msg,channel)
            packet = self.queue.pop()

    def removeChannel(self,chan):
        if self.SLchannels.has_key(chan):
            print "removing channel %s" % (chan)
            del self.SLchannels[chan]
        
    def announce(self, msg):
        if not self.is_listening(self.channel):
            return
        
        if self.verbose == 0:
            return

        if self.verbose == 1:
            if re.search("has arrived", msg):
                return
            if re.search("has departed", msg):
                return
        
        if self.verbose == 2:
            if not re.search("\]\s(\w*) (\w*):", msg):
                return
            
        try:
            self.connection.privmsg(self.channel, msg)
        except:
            print "privmsg failed"
                
    def sendSL(self, msg, chan=''):
        for ch in self.SLchannels.keys():
            if ch == chan:
                continue
            #print "sending %s to channel %s" % (msg, ch)
            AsyncSend(self.proxy,ch,msg,self).start()
            
    def on_join(self,c,e):
        source = e.source()
        nick = nm_to_n(source)
        channel = e.target()
        self.sendSL("%s has joined %s" % (nick, channel))
        
    def on_part(self,c,e):
        source = e.source()
        nick = nm_to_n(source)
        channel = e.target()
        self.sendSL("%s has left %s" % (nick, channel))
        
    def on_quit(self,c,e):
        source = e.source()
        nick = nm_to_n(source)
        channel = e.target()
        self.sendSL("%s has quit" % (nick))
        
    def on_kick(self,c,e):
        args = e.arguments()
        source = e.source()
        nick = nm_to_n(source)
        channel = e.target()
        self.sendSL("%s has kicked %s from %s [%s]" % (nick, args[0], channel, args[1]))
        
    def on_nick(self, c, e):
        nick = nm_to_n(e.source())
        newnick = e.target()
        self.sendSL("%s is now known as %s" % (nick, newnick))
        
    def get_version(self):
        """Returns the bot version.
        Used when answering a CTCP VERSION request.
        """
        return "VERSION SlackerBot by David Lucifer <david@lucifer.com>"
    
    def delay(self):
        time.sleep(random.randrange(2,5))
    
    def on_topic(self,c,e):
        args = e.arguments()
        source = e.source()
        nick = nm_to_n(source)
        
        if args[0] == self.channel:
            topic = args[1]
        else:
            topic = args[0]

        self.sendSL("%s changed the topic to %s" % (nick, topic))
        self.sendSL("Topic: %s" % (topic))

    def on_welcome(self, c, e):
        if (self.channel != None):
            c.join(self.channel)
            self.initQueue()
            
    def on_invite(self, c, e):
        channel = e.arguments()[0]
        self.delay()
        c.join(channel)

    def on_privmsg(self, c, e):
        args = e.arguments()
        msg = args[0]
        nick = nm_to_n(e.source())
        channel = e.target()
        
        output = self.do_command(nick, channel, msg)
        if output != None:
            self.privmsg_multiline(c,nick,output)

    def is_listening(self, channel):
        if self.voiced:
            return True
        mynick = self.connection.get_nickname()
        return self.channels.has_key(channel) and self.channels[channel].is_voiced(mynick)
    
    def i_am_mentioned(self, c, msg):
        msg = irc_lower(msg)
        mynick = irc_lower(c.get_nickname())
        pat = r"\b" + mynick + r"\b"
        return re.search(pat, msg)
        
    def on_ctcp(self, c, e):
        args = e.arguments()
        type = args[0]
        
        if type == 'ACTION':
            channel = e.target()            
            nick = nm_to_n(e.source())
            msg = args[1]
            self.sendSL("%s %s" % (nick, msg))
        else:
            return SingleServerIRCBot.on_ctcp(self, c, e)                          
        
    def on_pubmsg(self, c, e):
        args = e.arguments()
        msg = args[0]
        channel = e.target()
        source = nm_to_n(e.source())

        if self.is_listening(channel):
            self.sendSL(source + ": " + msg)

    def notice_multiline(self,c,channel,msg):
        self.delay()
        for x in string.split(msg,"\n"):
            c.notice(channel, x)
            time.sleep(1)
            
    def privmsg_multiline(self,c,nick,msg):
        self.delay()
        for x in string.split(msg,"\n"):
            c.privmsg(nick, x)
            time.sleep(1)

    def do_command(self, nick, channel, cmd):
        masters = ["Lucifer", "LuciferAFK", "DLucifer", "LuciferD" ]
        
        if not nick in masters:
            return
        
        if cmd == "die":
            self.die()
        elif cmd == "part" or cmd == "depart" or cmd == "leave":
            self.connection.part(channel)
        elif cmd == "report":
            return "Listening on queue '%s', using channel '%s'" % (self.queueName, self.SLchannels)
	elif cmd == "reset":
	    self.SLchannels = {}
	    return "channels reset"
        else:
            m = re.search(r"queue (.*)",cmd)
            if m:
                self.queueName = m.group(1)
                self.initQueue()
                return "switching to channel %s" % (self.queueName)
            else:
                m = re.search(r"verbose (.*)",cmd)
                if m:
                    try:
                        self.verbose = int(m.group(1))
                        return "set verbose to %d" % (self.verbose)
                    except:
                        return "not a number %s" % (m.group(1))
                else:
                    return "I don't understand " + cmd

    def start(self):
        self._connect()
        while 1:
            self.ircobj.process_once(1.0)
            self.check()
            
def main():
    import sys
    import getopt
    args = sys.argv[1:]
    optlist, args = getopt.getopt(args,'s:p:c:n:q:hv')
    port = 6667

    channel = None
    nickname = 'SLacker'
    server = 'localhost'
    queue = 'slacker'
    voiced = False
    
    for o in optlist:
        name = o[0]
        value = o[1]
        if name == '-s':
            server = value
        elif name == '-p':
            try:
                port = int(value)
            except ValueError:
                print "Error: Erroneous port."
                sys.exit(1)
        elif name == '-c':
            channel = value
        elif name == '-n':
            nickname = value
        elif name == '-q':
            queue = value
        elif name == '-v':
            voiced = True
            
    if(channel != '' and nickname != '' and server != ''):
        bot = SlackerBot(channel, nickname, server, port, queue, voiced)
        bot.start()
    else:
        print "Commandline options:"
        print
        print "  -s server"
        print "  [-p port]"
        print "  -n nick"
        print "  -c channel"
        print

if __name__ == "__main__":
    main()

