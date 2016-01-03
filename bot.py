from twisted.words.protocols import irc
from twisted.internet import reactor, protocol
from twisted.python import log

from string import ascii_lowercase, digits
from random import sample

from pylint.lint import Run
import requests

import re, sys, os
import functools
import subprocess

import fcntl as F


try:
    from urlparse import urlparse
except ImportError:
    # py3
    from urllib.parse import urlparse


FILE_FORMAT = {'python': '.py'}


def directory(path=None):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(self, *args, **kw):
            if not os.path.exists(path):
                os.makedirs(path)
            return func(self, path, *args, **kw)
        return wrapper
    return decorator


def source_code(paste):
    paste = paste + '/raw/'
    r = requests.get(paste, verify=False)
    if r.status_code == 200:
        return r.content


def rng(length=7):
    """Random name generator, used to name a file"""
    mix = ascii_lowercase + digits
    file_name = os.path.join(
            ''.join(sample(mix, length))
    )
    if not os.path.exists(file_name):
        file_name = file_name + FILE_FORMAT['python']
    return file_name


class Linter(object):
    def __init__(self, source_code):
        self.source_code = source_code
        self._file_name = rng()

    @directory(path='pastes/')
    def codeFile(self, path):
        """Writes source code into a file
        and returns written file name"""

        complete_path = os.path.join(path, self._file_name)
        
        try:
            # avoid race condition logic
	    # create file if doesnt exist| error if create and exists| open for write
            fd = os.open(complete_path, 
                    os.O_CREAT | 
                    os.O_EXCL | 
                    os.O_WRONLY)
        
            F.flock(fd, F.LOCK_EX)
            with os.fdopen(fd, 'w') as f:
                f.write(self.source_code)
        except OSError as oe:
            if oe.errno != errno.EXXIST:
                raise
        
        # the file existed so it gets the lock from the writing process.
        with file(complete_path, 'r') as f:
            F.flock(f, F.LOCK_EX)
        
        return complete_path
    
    def results(self, output=None):
        """Run pylint with the paste retrieved from the IRC
        and post the output to a pastebin site"""
 
        try:
            output = subprocess.check_output([
                'pylint',
                '--disable=C,R,RP0001,RP0002, \
                        RP0003,RP0101,RP0401, \
                        RP0701,RP0801',
                self.codeFile()
            ])
        except subprocess.CalledProcessError as cpe:
            output = cpe.output

        # lets post the output to a pastebin site
        # usually pylint results are quite big
        # and IRC servers may not handle full msg length
        
        return subprocess.check_output([
            'curl',
            '-F',
            'f:1={}'.format(output),
            'ix.io'
        ])

class Bot(irc.IRCClient):
    """Code Suggestions IRC bot"""
    
    nickname = 'lintbot' 
   
    def connectionMade(self):
        irc.IRCClient.connectionMade(self)

    def connectionLost(self, reason):
        irc.IRCClient.connectionLost(self, reason)

    def signedOn(self):
        """bot successfully signed on to server"""
        self.join(self.factory.channel) 

    def privmsg(self, user, channel, msg):
        """people msging bot"""
        user = user.split('!', 1)[0]
        pattern = r'(https?://dpaste\.de/\S+)' 

        # people pming bot
        if channel == self.nickname:
            msg = 'public channel only buddy!'
            self.msg(user, msg)
            return
        
        if msg == '%help':
            help_msg = '<my-nickname>: paste url'
            self.msg(channel, help_msg)
        elif msg == '%service':
            paste_service = 'I only support dpaste.de'
            self.msg(channel, paste_service)
        elif msg.startswith(self.nickname + ":"):
            paste = re.search(pattern, msg).group(0) # grab dpaste url out of the msg
            sc = source_code(paste)
            linter = Linter(sc) 
            self.msg(user, linter.results())
            
            if not paste: # not a dpaste.de url
                self.msg(user, paste_service)

class BotFactory(protocol.ClientFactory):
    """protocol instance will be created each time bot connect to server"""

    def __init__(self, channel):
        self.channel = channel

    def buildProtocol(self, addr):
        b = Bot()
        b.factory = self
        return b

    def clientConnectionList(self, connector, reason):
        """reconnect to server if disconnected"""
        connector.connect()

    def clientConnectionFailed(self, connector, reason):
        print('connection failed:', reason)
        reactor.stop()

def main(): 
    log.startLogging(sys.stdout)
    fact = BotFactory(sys.argv[1])
    reactor.connectTCP('irc.freenode.net', 6667, fact)

    reactor.run()

if __name__ == '__main__':
    main()
