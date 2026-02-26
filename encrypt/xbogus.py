# Source: JoeanAmier/TikTokDownloader (Apache-2.0)
# Modified: removed src.custom dependency

from base64 import b64encode
from hashlib import md5
from time import time
from urllib.parse import quote, urlencode

__all__ = ["XBogus"]

_DEFAULT_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


class XBogus:
    __string = "Dkdpgh4ZKsQB80/Mfvw36XI1R25-WUAlEi7NLboqYTOPuzmFjJnryx9HVGcaStCe="
    __array = (
        [None]*48 + list(range(10)) + [None]*39 + list(range(10, 16))
    )
    __canvas = 3873194319

    @staticmethod
    def disturb_array(a,b,e,d,c,f,t,n,o,i,r,_,x,u,s,l,v,h,g):
        arr = [0]*19
        arr[0]=a; arr[10]=b; arr[1]=e; arr[11]=d; arr[2]=c; arr[12]=f
        arr[3]=t; arr[13]=n; arr[4]=o; arr[14]=i; arr[5]=r; arr[15]=_
        arr[6]=x; arr[16]=u; arr[7]=s; arr[17]=l; arr[8]=v; arr[18]=h; arr[9]=g
        return arr

    @staticmethod
    def generate_garbled_1(a,b,c,d,e,f,g,h,i,j,k,l,m,n,o,p,q,r,s):
        arr = [0]*19
        arr[0]=a; arr[1]=k; arr[2]=b; arr[3]=l; arr[4]=c; arr[5]=m
        arr[6]=d; arr[7]=n; arr[8]=e; arr[9]=o; arr[10]=f; arr[11]=p
        arr[12]=g; arr[13]=q; arr[14]=h; arr[15]=r; arr[16]=i; arr[17]=s; arr[18]=j
        return "".join(map(chr, map(int, arr)))

    @staticmethod
    def generate_num(text):
        return [
            ord(text[i]) << 16 | ord(text[i+1]) << 8 | ord(text[i+2])
            for i in range(0, 21, 3)
        ]

    @staticmethod
    def generate_garbled_2(a, b, c):
        return chr(a) + chr(b) + c

    @staticmethod
    def generate_garbled_3(a, b):
        d = list(range(256)); c = 0; f = ""
        for i in range(256): d[i] = i
        for i in range(256):
            c = (c + d[i] + ord(a[i % len(a)])) % 256
            d[i], d[c] = d[c], d[i]
        t = c = 0
        for i in range(len(b)):
            t = (t+1)%256; c = (c+d[t])%256; d[t],d[c]=d[c],d[t]
            f += chr(ord(b[i]) ^ d[(d[t]+d[c])%256])
        return f

    def calculate_md5(self, input_string):
        if isinstance(input_string, str): arr = self.md5_to_array(input_string)
        elif isinstance(input_string, list): arr = input_string
        else: raise TypeError
        h = md5(); h.update(bytes(arr)); return h.hexdigest()

    def md5_to_array(self, md5_str):
        if isinstance(md5_str, str) and len(md5_str) > 32:
            return [ord(c) for c in md5_str]
        return [
            (self.__array[ord(md5_str[i])] << 4) | self.__array[ord(md5_str[i+1])]
            for i in range(0, len(md5_str), 2)
        ]

    def process_url_path(self, url_path):
        return self.md5_to_array(self.calculate_md5(self.md5_to_array(self.calculate_md5(url_path))))

    def generate_str(self, num):
        string = [num & 16515072, num & 258048, num & 4032, num & 63]
        string = [i >> j for i, j in zip(string, range(18,-1,-6))]
        return "".join(self.__string[i] for i in string)

    @staticmethod
    def handle_ua(a, b):
        d = list(range(256)); c = 0; result = bytearray(len(b))
        for i in range(256):
            c = (c + d[i] + ord(a[i % len(a)])) % 256
            d[i], d[c] = d[c], d[i]
        t = c = 0
        for i in range(len(b)):
            t = (t+1)%256; c = (c+d[t])%256; d[t],d[c]=d[c],d[t]
            result[i] = b[i] ^ d[(d[t]+d[c])%256]
        return result

    def generate_ua_array(self, user_agent: str, params: int) -> list:
        ua_key = ["\u0000", "\u0001", chr(params)]
        value = self.handle_ua(ua_key, user_agent.encode("utf-8"))
        value = b64encode(value)
        return list(md5(value).digest())

    def generate_x_bogus(self, query: list, params: int, user_agent: str, timestamp: int):
        ua_array = self.generate_ua_array(user_agent, params)
        array = [
            64, 0.00390625, 1, params,
            query[-2], query[-1], 69, 63,
            ua_array[-2], ua_array[-1],
            timestamp>>24&255, timestamp>>16&255, timestamp>>8&255, timestamp>>0&255,
            self.__canvas>>24&255, self.__canvas>>16&255,
            self.__canvas>>8&255, self.__canvas>>0&255,
            None,
        ]
        zero = 0
        for i in array[:-1]:
            zero ^= int(i)
        array[-1] = zero
        garbled = self.generate_garbled_1(*self.disturb_array(*array))
        garbled = self.generate_garbled_2(2, 255, self.generate_garbled_3("ÿ", garbled))
        return "".join(self.generate_str(i) for i in self.generate_num(garbled))

    def get_x_bogus(self, query, params=8, user_agent=_DEFAULT_UA, test_time=None):
        timestamp = int(test_time or time())
        q = self.process_url_path(
            urlencode(query, quote_via=quote) if isinstance(query, dict) else query
        )
        return self.generate_x_bogus(q, params, user_agent, timestamp)
