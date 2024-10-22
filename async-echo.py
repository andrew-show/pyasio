import asio
import socket


class Server:
    def __init__(self, address):
        self.__socket = asio.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.__socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.__socket.bind(address)
        self.__socket.listen(128)
        self.__socket.async_accept(self.__on_accept)

    def __on_accept(self, err, fd):
        class Session:
            def __init__(self, fd):
                self.__socket = fd
                self.__socket.async_recv(self.__on_read, 1024)

            def __on_read(self, err, buf):
                if err is not None:
                    print("async recv exception {}".format(err))
                else:
                    asio.async_write(self.__socket, self.__on_write, buf)

            def __on_write(self, err, size):
                if err is not None:
                    print("async_send exception {}".format(err))
                else:
                    self.__socket.async_recv(self.__on_read, 1024)

        if err is not None:
            print("accept exception {}".format(err))
        else:
            Session(fd)

        self.__socket.async_accept(self.__on_accept)




class Client:
    def __init__(self, address, concurrent):
        asio.post(lambda: self.__run(address, concurrent))

    async def __run(self, address, concurrent):
        class Session:
            def __init__(self, address):
                self.__stats = 0
                self.__socket = asio.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.__socket.async_connect(self.__on_connect, address)

            def __on_connect(self, err):
                if err is not None:
                    print("connect error {}".format(err))
                else:
                    print("{} -> {} connected".format(self.__socket.getsockname(), self.__socket.getpeername()))

                    asio.async_write(self.__socket, self.__on_write, b"hello")

            def __on_read(self, err, buf):
                if err is not None:
                    print("recv error {}".format(err))
                else:
                    self.__stats += 1
                    asio.async_write(self.__socket, self.__on_write, b"hello")

            def __on_write(self, err, size):
                if err is not None:
                    print("send error {}".format(err))
                else:
                    asio.async_read(self.__socket, self.__on_read, 5)

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
