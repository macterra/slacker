# Require simplejson to support serialization
# Unlike other language libraries, EVERYTHING is serialized with this
# This may also only support up to 16,000 bytes in a queue packet
# I know no Python so this is a very quick hack

import simplejson
import string
import base64
from socket import *
import sys
import re

class lwqueue:

	def __init__(self, server, queue):
		parts = string.split(server, ':')
		self.queue = queue
		self.server = parts[0]
		try:
			self.port = parts[1] 
		except:
			self.port = 3130
		self.socket = socket(AF_INET, SOCK_STREAM)
		self.socket.connect((self.server, int(self.port)))

	def push(self, data):
		self.socket.send(base64.encodestring("PUSH-" + self.queue + "-" + "{{serialized-json}}" + simplejson.dumps(data)) + "\n=====\n")
		data = self.socket.recv(1024)
		return data
	
	def pop(self):
		self.socket.send(base64.encodestring("POP-" + self.queue) + "\n=====\n")
		data = self.socket.recv(16000)
		data = base64.decodestring(data)

		if data == 'No such queue':
			return
		
		p = re.compile( '{{serialized-json}}' )
		data = p.sub('', data)
		if data:
			print "recvd data 2: [%s]" % (data)
			data = simplejson.loads(data)
		return data
