from tornado_irc import IRCConn, PING_TIMEOUT
import tornado

from datetime import datetime, timedelta

import signal
import time
import traceback
import logging
import sys
import socket

class Command(object):
    def __init__(self, predicate, f, docstring=None):
        self.f = f
        self.predicate = predicate
        self.docstring = docstring

    def __call__(self, bot, channel, user, message):
        ret = self.predicate(bot, channel, user, message)
        if ret:
            logging.info("responding to %s < %s> %s" % (channel, user, message))
            resp = self.f(bot, channel, user, message)
            if resp:
                bot.reply(channel, user, resp)
        return ret

def response(trigger):
    def _dec(f):
        def pred(bot, channel, user, message):
            return message.startswith(bot.nickname) and trigger in message
        return Command(pred, f)
    return _dec

def unrequested_response(trigger):
    def _dec(f):
        def pred(bot, channel, user, message):
            return trigger in message
        return Command(pred, f)
    return _dec

def command(trigger):
    def _dec(f):
        cmd = '%'+trigger
        def wrapper(f):
            def wrap(bot, channel, user, message):
                msg = ' '.join(message.split()[1:])
                return f(bot, channel, user, msg)
            return wrap
        def pred(bot, channel, user, message):
            s = message.split()
            if not len(s):
                return False
            return s[0] == cmd

        if f.__doc__:
            doc = '%s: %s' % (cmd, f.__doc__)
        else:
            doc = '%s' % cmd

        return Command(pred, wrapper(f), docstring=doc)
    return _dec

class IRCBot(IRCConn):
    def __init__(self, nickname, io_loop=None, owner="someone"):
        super(IRCBot, self).__init__(nickname, io_loop)
        self.commands = set()
        self.seen_exns = set()
        self.owner = owner
        for name in dir(self):
            f = getattr(self, name)
            if isinstance(f, Command):
                self.commands.add(f)

    def on_connect(self):
        logging.info("connected")
        for channel in self.channels:
            self.join(channel)

    def reply(self, channel, user, message):
        if channel:
            out = "%s: %s" % (user, message)
            self.chanmsg(channel, out)
        else:
            self.privmsg(user, message)

    def join(self, channel):
        super(IRCBot, self).join(channel)
        self.channels.add(channel)

    @command(trigger='help')
    def help(self, channel, user, message):
        """Show this message"""
        out = []
        for command in self.commands:
            if command.docstring:
                out.append(command.docstring)
        if len(out):
            return "I know the following commands: %s" % ('. '.join(out))
        elif len(self.commands):
            return "I know some commands, but have no documentation. :-("
        else:
            return "I know no commands."


    def run_commands(self, channel, user, message):
        try:
            for command in self.commands:
                if command(self, channel, user, message): break
        except Exception, e:
            s = traceback.format_exc()
            if s not in self.seen_exns:
                self.seen_exns.add(s)
                self.reply(channel, user, 'an error occurred. Ping %s about it.' % (self.owner,))
            print s

    def on_chanmsg(self, *args):
        self.run_commands(*args)

    def on_privmsg(self, *args):
        self.run_commands(None, *args)

    def on_close(self):
        timeout = 0.25
        connected = False
        while not connected:
            try:
                self.connect(self.server, self.port)
                connected = True
            except socket.error, e:
                logging.error(e)
                logging.info("backing off for %r" % timeout)
                time.sleep(timeout)
                timeout = min(timeout * 2, 5*60)

    def on_timeout(self):
        logging.info("Ping timeout after %r" %  PING_TIMEOUT)
        self.conn.close()

    def start(self, server, port, channels=None):
        channels = channels or []
        logging.basicConfig(level=logging.DEBUG,
                            format='[%(levelname)s %(asctime)s.%(msecs)d %(process)d] %(message)s',
                            datefmt="%Y%m%d %H:%M:%S",
                            stream=sys.stdout)
        logging.info("connecting to %s:%d" % (server, port))
        self.channels = set(channels)
        self.server = server
        self.port = port
        self.connect(server, port)
        signal.signal(signal.SIGINT,
                      lambda *a: self.io_loop.stop())
        self.io_loop.start()
