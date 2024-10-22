import asio

class Queue:
    def __init__(self):
        self.__queue = []
        self.__condition = asio.condition_variable()

    async def get(self):
        if not self.__queue:
            await self.__condition.wait()

        return self.__queue.pop(0)

    def put(self, message):
        self.__queue.append(message);
        self.__condition.signal()


class Test:
    def __init__(self):
        self.__queue = Queue()
        asio.post(self.__consume)
        asio.post(self.__produce)

    async def __produce(self):
        for i in range(1000):
            self.__queue.put(i)
            await asio.sched_yield()

        self.__queue.put(None)

    async def __consume(self):
        while True:
            msg = await self.__queue.get()
            if msg is None:
                break
            print(msg)


TestMutex()
asio.run_until_complete()
