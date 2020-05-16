import os
import sys
import errno
import time
import fcntl
from collections import namedtuple

try:
	import warnings
except ImportError:
	warnings = None

#A few exceptions to make errors readble and flexible
class IllegalArgumentError(ValueError):
	pass

class IllegalWithStatement(ValueError):
	pass

#Import on pylocksfile with "from pylocksfile import *"
__all__ = [ "pylocksfile" ]

__version__ = "0.0.6"

class lockInterval(object):
	def __init__(self):
		self._intervals = list()

		self.lock_interval_tuple = namedtuple('interval_tuple', ['lock_n' ,'n_locks'])

	@property
	def intervals(self):
		return self._intervals
		
	def __iter__(self):
		#Iterating over self._intervals
		return iter(self._intervals)

	def reset(self):
		self._intervals = list()

	def preprocessInput(self, interval):
		if not (isinstance(interval, int) or isinstance(interval, tuple) or isinstance(interval, list) or isinstance(interval, self.lock_interval_tuple)):
			raise IllegalArgumentError('lockInterval - interval argument is not a tuple, list or integer.')
		
		if isinstance(interval, int):
			if (interval < 0):
				raise IllegalArgumentError('lockInterval - integer interval must be  >=0')
			
			#Convert the single integer to list
			interval = self.lock_interval_tuple(interval, 1)
		
		if isinstance(interval, tuple) or isinstance(interval, list):
			if len(interval) != 2:
				raise IllegalArgumentError('lockInterval - interval tuple or list must have shape [2] - (start_lock, n_locks_ahead)')

			if (interval[0] < 0):
				raise IllegalArgumentError('lockInterval - interval first argument (lock_n) must be non-negative')					
			
			if (interval[1] <= 0):
				raise IllegalArgumentError('lockInterval - interval second argument (n_locks) must be positive')

			interval = self.lock_interval_tuple(interval[0], interval[1])

		return interval

	def inBound(self, lock_n):
		if not isinstance(lock_n, int):
			raise IllegalArgumentError('lockInterval - lock_n argument must be positive integer.')
		if not lock_n >= 0:
			#Avoid comparison of non-numeric
			raise IllegalArgumentError('lockInterval - lock_n argument must be positive integer.')

		for subInterval in self._intervals:
			#If lock_n is within the range of any subInterval, return True
			if (lock_n >= subInterval.lock_n) and (lock_n < subInterval.lock_n + subInterval.n_locks):
				return True

		#No match is found.
		return False

	def insertInterval(self, interval):
		#Create the interval and eliminate bad input
		interval = self.preprocessInput(interval)

		#Temporary list to hold the new intervals after the insertion operations
		intervals = list()

		for subInterval in self._intervals:
			if (subInterval.lock_n + subInterval.n_locks) <= interval.lock_n:
				#e.g. subInterval = (0,2), locks 0,1. interval = (2,1), locks 2. Out of bound, so insert.
				intervals.append(subInterval)
				continue
			elif subInterval.lock_n >= (interval.lock_n + interval.n_locks):
				#e.g. subInterval = (1,2), locks 1,2. interval = (0,1), locks 0. Out of bound, so insert.
				intervals.append(subInterval)
				continue
			elif (subInterval.lock_n + subInterval.n_locks) <= (interval.lock_n + interval.n_locks) and subInterval.lock_n >= interval.lock_n:
				#e.g. subInterval = (1,2), locks 1,2. interval = (1,2), locks 1,2. No need to insert, it is inbound.
				continue

			#If we got here, need to extend. Get new extended range and override the previous, shorter, interval
			mergedInterval_lock_n = min(subInterval.lock_n, interval.lock_n)
			mergedInterval_n_locks = max(subInterval.lock_n + subInterval.n_locks, interval.lock_n + interval.n_locks) - mergedInterval_lock_n
			interval = self.lock_interval_tuple(mergedInterval_lock_n, mergedInterval_n_locks)

		#Finally insert the new interval (may have been modified).
		intervals.append(interval)

		#Override the old intervals list
		self._intervals = intervals
		
		return

	def removeInterval(self, interval):
		#Create the interval and eliminate bad input
		interval = self.preprocessInput(interval)	

		#Temporary list to hold the new intervals after the insertion operations
		intervals = list()

		for subInterval in self._intervals:
			if (subInterval.lock_n + subInterval.n_locks) <= interval.lock_n:
				#e.g. subInterval = (0,2), locks 0,1. interval = (2,1), locks 2. Out of bound, so insert.
				intervals.append(subInterval)
				continue
			elif subInterval.lock_n >= (interval.lock_n + interval.n_locks):
				#e.g. subInterval = (1,2), locks 1,2. interval = (0,1), locks 0. Out of bound, so insert.
				intervals.append(subInterval)
				continue
			elif (subInterval.lock_n + subInterval.n_locks) <= (interval.lock_n + interval.n_locks) and subInterval.lock_n >= interval.lock_n:
				#e.g. subInterval = (1,2), locks 1,2. interval = (1,2), locks 1,2. No need to insert, it is inbound.
				continue

			#If we got here, need to decrease. This is the first ("left") interval after intersection
			mergedInterval_lock_n = min(subInterval.lock_n, interval.lock_n)
			mergedInterval_n_locks = max(subInterval.lock_n, interval.lock_n) - mergedInterval_lock_n
			
			#A new valid interval will only happen when lock_n is non-negative and interval length is positive, then reinsert to end of list (re-examined later)
			if mergedInterval_lock_n >= 0 and mergedInterval_n_locks > 0:
				self._intervals.append(self.lock_interval_tuple(mergedInterval_lock_n, mergedInterval_n_locks))

			#If we got here, need to decrease. This is the second ("right") interval after intersection
			mergedInterval_lock_n = min(subInterval.lock_n + subInterval.n_locks, interval.lock_n + interval.n_locks)
			mergedInterval_n_locks = max(subInterval.lock_n + subInterval.n_locks, interval.lock_n + interval.n_locks) - mergedInterval_lock_n
			
			#A new valid interval will only happen when lock_n is non-negative and interval length is positive, then reinsert to end of list (re-examined later)
			if mergedInterval_lock_n >= 0 and mergedInterval_n_locks > 0:
				self._intervals.append(self.lock_interval_tuple(mergedInterval_lock_n, mergedInterval_n_locks))

		#Override the previous intervals list
		self._intervals = intervals
		
		return


"""
pylocksfile class implementation

argument:
	- locksfile_path (str):
		Path of the file which will be used as lock, e.g. './lockfile.lock;. 
		If not provided, a temporary file will be created in '/tmp' directory with random name.
			* Do not use this file for read/write operations! It should only be accessed via this class methods

	- verbose (bool):
		Whether to print out read/write intervals and other messages regarding the operations.

	- l_id (str):
		ID of the correct instance. Used mainly as prefix of the printed information. 

"""
class pylocksfile(object):
	def __init__(self, locksfile_path = None, verbose = False, l_id = None):
		
		#If locksfile_path is None, create a temporary file in /tmp with random name (posix timestamp in ms)
		if locksfile_path is None:
			locksfile_path = os.path.join('/tmp', str(int(time.time() * 1000)) + '.lock')
		
		#If l_id is None, then give it a random name...for now process pid
		if l_id is None:
			lid = str(os.getpid())

		locksfile_path = os.path.abspath(locksfile_path)
		
		if not os.path.isdir(os.path.split(locksfile_path)[0]):
			raise IllegalArgumentError('pylocksfile - locksfile_path directory path does not exist.')
		
		if not isinstance(verbose, bool):
			raise IllegalArgumentError('pylocksfile - verbose argument is not boolean (True/False).')
		
		if not isinstance(locksfile_path, str):
			raise IllegalArgumentError('pylocksfile - l_id argument is not str.')

		#Get absolute path to the file
		self._locksfile_path =  os.path.abspath(locksfile_path)
		
		#Determine if inside information will be printed.
		self._verbose = verbose

		#self._fd = None
		self._fd  = os.open(self._locksfile_path, os.O_CREAT | os.O_TRUNC | os.O_RDWR)

		self._readLockIntervals = lockInterval()
		self._writeLockIntervals = lockInterval()
		
		#For __enter__ and __exit__ recall
		self._current_lock_n = list()

		self._l_id = l_id

		return

	@property
	def locksfile_path(self):
		return self._locksfile_path

	@property
	def l_id(self):
		return self._l_id

	@property
	def verbose(self):
		return self._verbose

	@verbose.setter
	def verbose(self, new_verbose):
		self._verbose = new_verbose
	

	def acquire(self, writeLock = False, lock_n = 0, blocking = True):
		if not isinstance(writeLock, bool):
			raise IllegalArgumentError('writeLock must be boolean')
		if not isinstance(blocking, bool):
			raise IllegalArgumentError('blocking must be boolean')

		#self.printVerbose('Attemping to lock ->' + str(lock_n))

		#Create the interval of the lock. Will raise Exception on invalid input.
		lock_interval = self._readLockIntervals.preprocessInput(lock_n)

		#Set the lock type
		lock_type = (fcntl.LOCK_EX if writeLock else fcntl.LOCK_SH) | (0 if blocking else fcntl.LOCK_NB)
		
		try:
			#fcntl.lockf(fd, lock_type, lock_interval.n_locks, lock_interval.lock_n, 0) #len, start, whence = 0
			fcntl.lockf(self._fd, lock_type, lock_interval.n_locks, lock_interval.lock_n, 0) #fd, cmd, len, start, whence = 0

		except (IOError, OSError) as e:
			
			self.printVerbose("Exception" + str(e))
			
			if e.errno == errno.EDEADLK:
				self.printVerbose('Deadlock detected by os. By linux policy - lock request removed for ' + str(lock_interval))

			return False

		#Update list of locks. - last operation counts.
		if writeLock:
			self._writeLockIntervals.insertInterval(lock_interval)
			self._readLockIntervals.removeInterval(lock_interval)
		else:
			self._readLockIntervals.insertInterval(lock_interval)
			self._writeLockIntervals.removeInterval(lock_interval)

		if writeLock:
			self.printVerbose('Write lock acquired ->' + str(lock_n))
		else:
			self.printVerbose('Read lock acquired ->' + str(lock_n))

		self.printVerbose('read Locked ->' + str(self._readLockIntervals.intervals))
		self.printVerbose('write Locked ->' + str(self._writeLockIntervals.intervals))
		
		return True

	def release(self, lock_n = None):

		if lock_n is None:
			
			#If lock_n is None, release all the recorded locks, and reset list
			lock_intervals = self._readLockIntervals.intervals + self._writeLockIntervals.intervals
			
			#Clear all the records
			self._readLockIntervals.reset()
			self._writeLockIntervals.reset()
		else:
			#Create the list of the interval of the lock. Will raise Exception on invalid input.
			lock_intervals = [self._readLockIntervals.preprocessInput(lock_n)] 
			
			#Remove interval.
			self._readLockIntervals.removeInterval(lock_intervals[0])
			self._writeLockIntervals.removeInterval(lock_intervals[0])

		self.printVerbose('Releasing ->' + str(lock_n))

		if self._fd:
			
			#Iterate over the interval of locks
			for lock_i in lock_intervals:

				#Free the locks in current interval
				fcntl.lockf(self._fd, fcntl.LOCK_UN, lock_i.n_locks, lock_i.lock_n, 0)

		#self.printVerbose('read Locked ->' + str(self._readLockIntervals.intervals))
		#self.printVerbose('write Locked ->' + str(self._writeLockIntervals.intervals))

		return

	#Note - When using WITH statement, call must be blocking
	def __call__(self, writeLock = False, lock_n = 0):
		#save for future release. 
		self._current_lock_n.append((writeLock, lock_n))
		
		return self

	def __enter__(self):
		self.printVerbose('With statement (always blocking). Locking ->' + str(self._current_lock_n[-1]))
		
		#Get saved arguments
		writeLock, lock_n = self._current_lock_n[-1] 
		
		self.acquire(writeLock = writeLock, lock_n = lock_n)
		
		return self

	def __exit__(self, exc_type, exc_value, traceback):
		self.printVerbose('With statement. unLocking ->' + str(self._current_lock_n[-1]))
		
		#release last lock_n
		_, lock_n = self._current_lock_n[-1]
		
		self.release(lock_n = lock_n)
		
		return None

	def __del__(self):
		self.printVerbose('Deleting. Release all locks')
		
		#Release all
		self.release(lock_n = None)
		
		return None

	def printVerbose(self, msg):
		if self._verbose:
			print(str(type(self)), '-' , str(self._l_id) , '-', msg)




