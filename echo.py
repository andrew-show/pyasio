import asio
import socket


class Server:
    def __init__(self, address):
        self.__socket = asio.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.__socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.__socket.bind(address)
        self.__socket.listen(128)
        asio.post(self.__run)

    async def __run(self):
        class Session:
            def __init__(self, fd):
                self.__socket = fd
                asio.post(self.__run)

            async def __run(self):
                print("accept session {} ...".format(self.__socket.getpeername()))
                while True:
                    buf = await self.__socket.recv(1024)
                    await self.__socket.send(buf)

        while True:
            fd = await self.__socket.accept()
            Session(fd)


class Client:
    def __init__(self, address, concurrent):
        asio.post(lambda: self.__run(address, concurrent))

    async def __run(self, address, concurrent):
        class Session:
            def __init__(self, address):
                self.__stats = 0
                self.__socket = asio.socket(socket.AF_INET, socket.SOCK_STREAM)
                asio.post(lambda: self.__run(address))

            async def __run(self, address):
                await self.__socket.connect(address)
                print("{} -> {} connected".format(self.__socket.getsockname(), self.__socket.getpeername()))

                while True:
                    buf = b"hello"
                    await asio.write(self.__socket, buf)
                    await asio.read(self.__socket, len(buf))
                    self.__stats += 1

                self.__done = True

            @property
            def stats(self):
                return self.__stats

        await asio.sleep(1)
        session_list = [Session(address) for i in range(concurrent)]

        stats = [ session.stats for session in session_list ]
        while True:
            await asio.sleep(1)
            for i in range(len(stats)):
                diff = session_list[i].stats - stats[i]
                stats[i] = session_list[i].stats
                print("{}".format(diff), end=' ')

            print("")


address = ("127.0.0.1", 10001)
server = Server(address)
client = Client(address, 5)

asio.run_until_complete()
