
from collections import defaultdict
from datetime import (
    datetime,
    timedelta,
)

from random import choice

import signal
import time

import tornado.ioloop
from tornado_irc import IRCConn

class Command(object):
    def __init__(self, predicate, f, docstring=None):
        self.f = f
        self.predicate = predicate
        self.docstring = docstring

    def __call__(self, bot, channel, user, message):
        ret = self.predicate(bot, channel, user, message)
        if ret:
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

def command(trigger):
    def _dec(f):
        cmd = '%'+trigger
        def wrapper(f):
            def wrap(bot, channel, user, message):
                return f(bot, channel, user, message[len(cmd):].strip())
            return wrap
        def pred(bot, channel, user, message):
            return message.split()[0] == cmd

        if f.__doc__:
            doc = '%s: %s' % (cmd, f.__doc__)
        else:
            doc = '%s' % cmd

        return Command(pred, wrapper(f), docstring=doc)
    return _dec

class LunchBot(IRCConn):
    def __init__(self, nickname, io_loop=None, channels=[]):
        self.channels = set(channels)
        super(LunchBot, self).__init__(nickname, io_loop)
        self.timers = defaultdict(dict)
        self.commands = set()
        for name in dir(self):
            f = getattr(self, name)
            if isinstance(f, Command):
                self.commands.add(f)

    def on_connect(self):
        print "connected"
        for channel in self.channels:
            self.join(channel)

    def reply(self, channel, user, message):
        out = "%s: %s" % (user, message)
        self.chanmsg(channel, out)

    def join(self, channel):
        super(LunchBot, self).join(channel)
        self.channels.add(channel)

    @response(trigger='botsnack')
    def botsnack(self, channel, user, message):
        return choice([":)", ":3", "thanks!", "tasty!"])

    @response(trigger='<3')
    def heart(self, channel, user, message):
        return '<3'

    @command(trigger='time')
    def add_timer(self, channel, user, message):
        """ Add a timer"""
        when, sep, msg = message.partition(' ')
        try:
            when = int(when)
        except ValueError, TypeError:
            return "'%s' is not an integer" % (when,)

        if msg in self.timers[user]:
            return "there is already a timer for '%s'" % (msg,)

        end = choice(["%s is done", "%s is ready", "%s is finished"]) % msg

        end_time = datetime.now()+timedelta(minutes=when)
        end_ts = time.mktime(end_time.timetuple())

        def response():
            self.reply(channel, user, end)
            del self.timers[user][msg]

        cb = self.io_loop.add_timeout(end_ts, response)
        self.timers[user][msg] = (cb, end_ts)
        return "okay! starting %d minute timer for '%s'." % (when, msg)

    @command(trigger='list')
    def list_timers(self, channel, user, message):
        """List all your timers"""
        s = []
        for msg, (cb, end_time) in self.timers[user].iteritems():
            done = int(end_time - time.time())
            out = "'%s' in %02d:%02d" % (msg, done / 60, done % 60)
            s.append(out)
        if s:
            return 'you have the following timers: %s' % (', '.join(s),)
        else:
            return 'you have no timers running.'

    @command(trigger='cancel')
    def cancel_timer(self, channel, user, message):
        """Cancels a timer"""
        if message not in self.timers[user]:
            return "you don't have a timer for '%s'!" % (message,)
        cb, _ = self.timers[user][message]
        self.io_loop.remove_timeout(cb)
        del self.timers[user][message]
        return "Okay, removing timer for '%s'." % (message,)

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

    def on_chanmsg(self, *args):
        try:
            for command in self.commands:
                if command(self, *args): break
        except Exception, e:
            self.reply('an error occurred. Ping rpearl about it.')

if __name__ == '__main__':
    c = LunchBot('lunchbot_', channels=["#cslunchbot-test"])
    c.connect('irc.freenode.net', 6667)

    signal.signal(signal.SIGINT, lambda *args: tornado.ioloop.IOLoop.instance().stop())
    tornado.ioloop.IOLoop.instance().start()
