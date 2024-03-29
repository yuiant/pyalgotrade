# PyAlgoTrade
#
# Copyright 2011-2018 Gabriel Martin Becedillas Ruiz
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
.. moduleauthor:: Gabriel Martin Becedillas Ruiz <gabriel.becedillas@gmail.com>
"""

import os
import signal

from pyalgotrade import dispatchprio
from pyalgotrade import logger as logging
from pyalgotrade import observer, utils

logger = logging.getLogger(__name__)


# This class is responsible for dispatching events from multiple subjects, synchronizing them if necessary.
class Dispatcher(object):
    def __init__(self):
        self.__subjects = []
        self.__stop = False
        self.__startEvent = observer.Event()
        self.__idleEvent = observer.Event()
        self.__currDateTime = None

    # Returns the current event datetime. It may be None for events from realtime subjects.
    def getCurrentDateTime(self):
        return self.__currDateTime

    def getStartEvent(self):
        return self.__startEvent

    def getIdleEvent(self):
        return self.__idleEvent

    def stop(self):
        self.__stop = True

    def getSubjects(self):
        return self.__subjects

    def addSubject(self, subject):
        # Skip the subject if it was already added.
        if subject in self.__subjects:
            return

        # If the subject has no specific dispatch priority put it right at the end.
        if subject.getDispatchPriority() is dispatchprio.LAST:
            self.__subjects.append(subject)
        else:
            # Find the position according to the subject's priority.
            pos = 0
            for s in self.__subjects:
                if s.getDispatchPriority() is dispatchprio.LAST or subject.getDispatchPriority() < s.getDispatchPriority():
                    break
                pos += 1
            self.__subjects.insert(pos, subject)

        subject.onDispatcherRegistered(self)

    # Return True if events were dispatched.
    def __dispatchSubject(self, subject, currEventDateTime):
        ret = False
        # Dispatch if the datetime is currEventDateTime of if its a realtime subject.
        if not subject.eof() and subject.peekDateTime() in (None, currEventDateTime):
            ret = subject.dispatch() is True
        return ret

    # Returns a tuple with booleans
    # 1: True if all subjects hit eof
    # 2: True if at least one subject dispatched events.
    def __dispatch(self):
        smallestDateTime = None
        eof = True
        eventsDispatched = False

        # Scan for the lowest datetime.
        for subject in self.__subjects:
            if not subject.eof():
                eof = False
                smallestDateTime = utils.safe_min(smallestDateTime, subject.peekDateTime())
            elif os.getenv('PYALGOTRADE_NEVER_STOP'):
                logger.info('Subject %s is reaching eof...', subject)
                logger.info(('Dispatcher is killing main process '
                             'since PYALGOTRADE_NEVER_STOP is set'))
                os.kill(os.getpid(), signal.SIGTERM)

        # Dispatch realtime subjects and those subjects with the lowest datetime.
        if not eof:
            self.__currDateTime = smallestDateTime

            for subject in self.__subjects:
                if self.__dispatchSubject(subject, smallestDateTime):
                    eventsDispatched = True
        return eof, eventsDispatched

    def run(self):
        try:
            for subject in self.__subjects:
                logger.info('Starting subject: %s', subject)
                subject.start()

            self.__startEvent.emit()

            while not self.__stop:
                eof, eventsDispatched = self.__dispatch()
                if eof:
                    logger.info('eof:{}'.format(eventsDispatched))
                    self.__stop = True
                elif not eventsDispatched:
                    self.__idleEvent.emit()
        except Exception as e:
            logger.error(e)

        finally:
            logger.info('Dispatcher reaching finally block...')
            logger.info('dispatcher subs:{}'.format(self.__subjects))

            if os.getenv('PYALGOTRADE_NEVER_STOP'):
                logger.info(('Dispatcher is killing main process '
                             'since PYALGOTRADE_NEVER_STOP is set'))
                os.kill(os.getpid(), signal.SIGTERM)

            # There are no more events.
            self.__currDateTime = None

            for subject in self.__subjects:
                logger.info('Dispatcher is stopping subject %s', subject)
                subject.stop()
                logger.info(
                    'Dispatcher is stopping subject %s (done!)', subject)
            for subject in self.__subjects:
                logger.info('Dispatcher is joining subject %s', subject)
                subject.join()
                logger.info('Dispatcher is joining subject %s (done!)', subject)

            if os.getenv('PYALGOTRADE_NEVER_STOP'):
                self.run()
