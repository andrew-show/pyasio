import sys
import types
import time
import heapq
import selectors
import socket as net
import threading
import traceback


class Await:
    def __init__(self, trap):
        self.__trap = trap

    def __await__(self):
        result = yield self.__trap
        return result


class PriorityQueue:
    def __init__(self):
        self.__queue = []

    def add(self, item):
        if getattr(item, "heap_index", None) is not None:
            raise ValueError("The item is already add to a priority queue")

        i = len(self.__queue)
        self.__queue.append(item)
        self.__up(i)

    def remove(self, item):
        i = getattr(item, "heap_index", None)
        if i is None or i < 0 or i >= len(self.__queue):
            return False

        item.heap_index = None
        item = self.__queue.pop()
        if i < len(self.__queue):
            self.__queue[i] = item
            self.__up(i)
            if item.heap_index == i:
                self.__down(i)

        return True

    def popitem(self):
        if not self.__queue:
            return None

        result = self.__queue[0]
        result.heap_index = None

        item = self.__queue.pop()
        if self.__queue:
            self.__queue[0] = item
            self.__down(0)

        return result

    def __len__(self):
        return len(self.__queue)

    def __bool__(self):
        return len(self.__queue) > 0

    def __getitem__(self, index):
        return self.__queue[index]

    def __up(self, index):
        i = index
        item = self.__queue[i]
        while i > 0:
            n = (i - 1) >> 1
            next_item = self.__queue[n]
            if not item < next_item:
                break

            self.__queue[i] = next_item
            next_item.heap_index = i
            i = n

        self.__queue[i] = item
        item.heap_index = i

    def __down(self, index):
        i = index
        item = self.__queue[i]
        while True:
            n = (i << 1) + 1
            if n >= len(self.__queue):
                break

            if (n + 1) < len(self.__queue):
                if self.__queue[n + 1] < self.__queue[n]:
                    n = n + 1

            next_item = self.__queue[n]
            if not next_item < item:
                break

            next_item.heap_index = i
            self.__queue[i] = next_item
            i = n

        self.__queue[i] = item
        item.heap_index = i


class SuspendException(Exception):
    pass


class Timer:
    def __init__(self, task, seconds):
        self.__task = task
        self.__expire = time.monotonic() + seconds

    def __lt__(self, rhs):
        return self.expire < rhs.expire

    def cancel(self):
        get_event_loop().cancel_timer(self)

    @property
    def expire(self):
        return self.__expire

    @property
    def task(self):
        return self.__task


class EventLoop:
    def __init__(self):
        self.__selector = selectors.DefaultSelector()
        self.__task_list = []
        self.__timer_queue = PriorityQueue()
        self.__num_fds = 0
        self.__num_coroutines = 0
        self.__current = None

    def __run_tasks(self):
        if not self.__task_list:
            return
        task_list = self.__task_list
        self.__task_list = []
        for task in task_list:
            self.__exec(task)

    def __run_expired(self):
        if not self.__timer_queue:
            return
        now = time.monotonic()
        while self.__timer_queue:
            if self.__timer_queue[0].expire > now:
                break
            timer = self.__timer_queue.popitem()
            self.__exec(timer.task)

    def __select_events(self):
        seconds = None
        if self.__task_list:
            seconds = 0
        elif self.__timer_queue:
            seconds = self.__timer_queue[0].expire - time.monotonic()

        if self.__num_fds > 0:
            for key, events in self.__selector.select(seconds):
                notify = key.data
                notify(events)
        else:
            sleep(seconds if seconds is not None else 1)

    def __exec(self, task):
        if isinstance(task, types.CoroutineType):
            ctxt = task
        else:
            try:
                ctxt = task()
            except:
                print("exec {}".format(sys.exc_info()))
                return

            if not isinstance(ctxt, types.CoroutineType):
                return

        self.__num_coroutines += 1
        self.resume(ctxt)

    def resume(self, ctxt, result=None):
        self.__current = ctxt
        while True:
            try:
                trap = ctxt.throw(result) if isinstance(result, Exception) else ctxt.send(result)
            except Exception as e:
                self.__num_coroutines -= 1
                if not isinstance(e, StopIteration):
                    print("resume {} {}".format(ctxt, sys.exc_info()))
                break

            try:
                result = trap(ctxt)
            except SuspendException:
                break
            except Exception as e:
                result = e

        self.__current = None

    def register(self, fd, events, data):
        self.__selector.register(fd, events, data)
        self.__num_fds += 1

    def unregister(self, fd):
        self.__selector.unregister(fd)
        self.__num_fds -= 1

    def modify(self, fd, events, data):
        self.__selector.modify(fd, events, data)

    def post(self, task):
        self.__task_list.append(task)

    def expires_after(self, task, seconds):
        timer = Timer(task, seconds)
        self.__timer_queue.add(timer)
        return timer

    def cancel_timer(self, timer):
        self.__timer_queue.remove(timer)

    def sleep(self, seconds):
        def __await(ctxt):
            self.expires_after(lambda: self.resume(ctxt), seconds)
            raise SuspendException()

        return Await(__await)

    def sched_yield(self):
        def __await(ctxt):
            self.post(lambda: self.resume(ctxt))
            raise SuspendException()

        return Await(__await)

    def current(self):
        return self.__current

    def run(self):
        while True:
            self.__run_tasks()
            self.__select_events()
            self.__run_expired()

    def run_until_complete(self):
        while self.__num_fds > 0 or self.__num_coroutines or self.__task_list or self.__timer_queue:
            self.__run_tasks()
            self.__select_events()
            self.__run_expired()


thread = threading.local()


def get_event_loop():
    event_loop = getattr(thread, "event_loop", None)
    if event_loop is None:
        event_loop = EventLoop()
        thread.event_loop = event_loop
    return event_loop


def post(task):
    get_event_loop().post(task)


def expires_after(task, seconds):
    return get_event_loop().expires_after(task, seconds)


def sleep(seconds):
    return get_event_loop().sleep(seconds)


def sched_yield():
    return get_event_loop().sched_yield()


def resume(ctxt, result=None):
    return get_event_loop().resume(ctxt, result)


def run():
    return get_event_loop().run()


def run_until_complete():
    return get_event_loop().run_until_complete()


def current():
    return get_event_loop().current()


class Socket:
    def __init__(self, fd):
        self.__socket = fd
        self.__socket.setblocking(False)
        self.__events = 0
        self.__on_notify = {}

    def bind(self, *args):
        return self.__socket.bind(*args)

    def listen(self, *args):
        return self.__socket.listen(*args)

    def getsockopt(self, *args, **kwargs):
        return self.__socket.getsockopt(*args, **kwargs)

    def setsockopt(self, *args, **kwargs):
        return self.__socket.setsockopt(*args, **kwargs)

    def getsockname(self):
        return self.__socket.getsockname()

    def getpeername(self):
        return self.__socket.getpeername()

    def connect(self, address):
        def __await(ctxt):
            try:
                self.__socket.connect(address)
            except BlockingIOError:
                def __wakeup():
                    self.__unregister(selectors.EVENT_WRITE)
                    err = self.__socket.getsockopt(net.SOL_SOCKET, net.SO_ERROR)
                    resume(ctxt, None if err == 0 else OSError(err, os.strerror(err)))

                self.__register(selectors.EVENT_WRITE, __wakeup)
                raise SuspendException()

        return Await(__await)

    def accept(self):
        def __await(ctxt):
            try:
                fd, addr = self.__socket.accept()
            except BlockingIOError:
                def __wakeup():
                    self.__unregister(selectors.EVENT_READ)
                    try:
                        fd, addr = self.__socket.accept()
                    except Exception as e:
                        resume(ctxt, e)
                    else:
                        resume(ctxt, Socket(fd))

                self.__register(selectors.EVENT_READ, __wakeup)
                raise SuspendException()
            else:
                return Socket(fd)

        return Await(__await)

    def send(self, buf, flags=0):
        def __await(ctxt):
            try:
                size = self.__socket.send(buf, flags)
            except BlockingIOError:
                def __wakeup():
                    self.__unregister(selectors.EVENT_WRITE)
                    try:
                        size = self.__socket.send(buf, flags)
                    except Exception as e:
                        resume(ctxt, e)
                    else:
                        resume(ctxt, size)

                self.__register(selectors.EVENT_WRITE, __wakeup)
                raise SuspendException()
            else:
                return size

        return Await(__await)

    def recv(self, bufsize, flags=0):
        def __await(ctxt):
            try:
                return self.__socket.recv(bufsize, flags)
            except BlockingIOError:
                def __wakeup():
                    self.__unregister(selectors.EVENT_READ)
                    try:
                        buf = self.__socket.recv(bufsize, flags)
                    except Exception as e:
                        resume(ctxt, e)
                    else:
                        resume(ctxt, buf)

                self.__register(selectors.EVENT_READ, __wakeup)
                raise SuspendException()

        return Await(__await)

    def async_connect(self, callback, address):
        try:
            self.__socket.connect(address)
        except BlockingIOError:
            def __wakeup():
                self.__unregister(selectors.EVENT_WRITE)
                err = self.__socket.getsockopt(net.SOL_SOCKET, net.SO_ERROR)
                callback(None if err == 0 else OSError(err, os.strerror(err)))

            self.__register(selectors.EVENT_WRITE, __wakeup)
        except Exception as e:
            post(lambda: callback(e))
        else:
            post(lambda: callback(None))

    def async_accept(self, callback):
        try:
            fd, addr = self.__socket.accept()
        except BlockingIOError:
            def __wakeup():
                self.__unregister(selectors.EVENT_READ)
                try:
                    fd, addr = self.__socket.accept()
                except Exception as e:
                    callback(e, None)
                else:
                    callback(None, Socket(fd))

            self.__register(selectors.EVENT_READ, __wakeup)
        except Exception as e:
            post(lambda: callback(e, None))
        else:
            post(lambda: callback(None, Socket(fd)))

    def async_send(self, callback, buf, flags=0):
        try:
            size = self.__socket.send(buf, flags)
        except BlockingIOError:
            def __wakeup():
                 self.__unregister(selectors.EVENT_WRITE)
                 try:
                     size = self.__socket.send(buf, flags)
                 except Exception as e:
                     callback(e, size)
                 else:
                     callback(None, size)

            self.__register(selectors.EVENT_WRITE, __wakeup)
        except Exception as e:
            post(lambda: callback(e, 0))
        else:
            post(lambda: callback(None, size))

    def async_recv(self, callback, bufsize, flags=0):
        try:
            buf = self.__socket.recv(bufsize, flags)
        except BlockingIOError:
            def __wakeup():
                self.__unregister(selectors.EVENT_READ)
                try:
                    buf = self.__socket.recv(bufsize, flags)
                except Exception as e:
                    callback(e, None)
                else:
                    callback(None, buf)

            self.__register(selectors.EVENT_READ, __wakeup)
        except Exception as e:
            post(lambda: callback(e, None))
        else:
            post(lambda: callback(None, buf))

    def __register(self, event, callback):
        events = self.__events | event
        if self.__events == 0:
            get_event_loop().register(self.__socket, events, self.__notify)
        else:
            get_event_loop().modify(self.__socket, events, self.__notify)
        self.__events = events
        self.__on_notify[event] = callback

    def __unregister(self, event):        
        self.__events &= ~event
        if self.__events == 0:
            get_event_loop().unregister(self.__socket)
        else:
            get_event_loop().modify(self.__socket, self.__events, self.__notify)
        del self.__on_notify[event]

    def __notify(self, events):
        if events & selectors.EVENT_READ:
            self.__on_notify[selectors.EVENT_READ]()
        if events & selectors.EVENT_WRITE:
            self.__on_notify[selectors.EVENT_WRITE]()


async def read(socket, size, flags=0):
    result=bytes()
    while size > 0:
        buf = await socket.recv(size, flags)
        if len(buf) == 0:
            raise EOFError("Peer closed connection")
        result += buf
        size -= len(buf)

    return result


async def write(socket, buf, flags=0):
    size = 0
    while size < len(buf):
        size += await socket.send(buf[size:], flags)

    return size


def async_read(socket, callback, size, flags=0):
    class AsyncRead:
        def __init__(self):
            self.__buf = bytes()
            socket.async_recv(self.__notify, size, flags)

        def __notify(self, err, buf):
            if err is not None:
                callback(err, self.__buf)
            elif len(buf) == 0:
                callback(EOFError("Peer closed connection"), self.__buf)
            else:
                self.__buf += buf
                if len(self.__buf) == size:
                    callback(None, self.__buf)
                else:
                    socket.async_recv(self.__notify, size - len(self.__buf), flags)

    AsyncRead()


def async_write(socket, callback, buf, flags=0):
    class AsyncWrite:
        def __init__(self):
            self.__size = 0
            socket.async_send(self.__notify, buf, flags)

        def __notify(self, err, size):
            if err is not None:
                callback(err, self.__size)
            else:
                self.__size += size
                if self.__size == len(buf):
                    callback(None, self.__size)
                else:
                    socket.async_send(self.__notify, buf[self.__size:], flags)

    AsyncWrite()


def socket(family, type):
    return Socket(net.socket(family, type))


class Mutex:
    def __init__(self):
        self.__owner = None
        self.__wait_queue = []

    def lock(self):
        def __await(ctxt):
            if self.__owner is None:
                self.__owner = ctxt
            else:
                def __wakeup():
                    self.__owner = ctxt
                    post(lambda: resume(ctxt))

                self.__wait_queue.append(__wakeup)
                raise SuspendException()

        return Await(__await)

    def unlock(self):
        if self.__owner != current():
            raise ValueError("The lock is not owned by current coroutine {} {}".format(self.__owner, current()))

        if self.__wait_queue:
            wakeup = self.__wait_queue.pop(0)
            wakeup()
        else:
            self.__owner = None

    def __async_lock(self, ctxt, callback):
        if self.__owner is None:
            self.__owner = ctxt
            callback()
        else:
            def __wakeup():
                self.__owner = ctxt
                callback()

            self.__wait_queue.append(__wakeup)
    
    def __async_unlock(self, ctxt):
        if self.__owner != ctxt:
            raise ValueError("The lock is not owned by current coroutine {} {}".format(self.__owner, ctxt))

        if self.__wait_queue:
            wakeup = self.__wait_queue.pop(0)
            wakeup()
        else:
            self.__owner = None


class ConditionVariable:
    def __init__(self):
        self.__wait_queue = []

    def wait(self, mutex=None):
        def __await(ctxt):
            if mutex is None:
                self.__wait_queue.append(lambda: post(lambda: resume(ctxt)))
            else:
                mutex._Mutex__async_unlock(ctxt)
                self.__wait_queue.append(lambda: mutex._Mutex__async_lock(ctxt, lambda: post(lambda: resume(ctxt))))

            raise SuspendException()

        return Await(__await)

    def timed_wait(self, seconds, mutex=None):
        def __await(ctxt):
            def __timeout():
                try:
                    i = self.__wait_queue.index(__wakeup)
                except ValueError:
                    pass
                else:
                    self.__wait_queue.pop(i)
                    if mutex is None:
                        resume(ctxt, False)
                    else:
                        mutex._Mutex__async_lock(ctxt, lambda: resume(ctxt, False))

            def __wakeup():
                timer.cancel()
                if mutex is None:
                    post(lambda: resume(ctxt, True))
                else:
                    mutex._Mutex__async_lock(ctxt, lambda: post(lambda: resume(ctxt, True)))

            if mutex is not None:
                mutex._Mutex__async_unlock(ctxt)

            timer = expires_after(__timeout, seconds)
            self.__wait_queue.append(__wakeup)
            raise SuspendException()

        return Await(__await)

    def signal(self):
        if self.__wait_queue:
            wakeup = self.__wait_queue.pop(0)
            wakeup()

    def broadcast(self):
        wait_queue = self.__wait_queue
        self.__wait_queue = []
        for wakeup in wait_queue:
            wakeup()

def mutex():
    return Mutex()


def condition_variable():
    return ConditionVariable()
