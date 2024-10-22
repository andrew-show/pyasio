import asio

class Test:
    def __init__(self):
        self.__signal_exit = False
        self.__mutex = asio.mutex()
        self.__condition = asio.condition_variable()
        asio.post(self.__signal)
        asio.post(self.__wait)

    async def __signal(self):
        await asio.sleep(0.2)
        await self.__mutex.lock()
        print("locked")
        self.__condition.signal()
        await asio.sleep(5)
        print("sleep done and unlock")
        self.__mutex.unlock()
        
    async def __wait(self):
        await self.__mutex.lock()
        print("wait")
        r = await self.__condition.timed_wait(1, self.__mutex)
        print("wait condition wait done {}".format(r))
        self.__mutex.unlock()

Test()
asio.run_until_complete()
