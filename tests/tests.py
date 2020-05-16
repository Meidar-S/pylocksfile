import os
from multiprocessing import Pool, Manager, Lock, Queue
from functools import partial
import time
import numpy as np
import operator

from pylocksfile import pylocksfile


class procRace():
	def __init__(self, procIdx, n_tracks, n_races):
		self.procIdx = procIdx
		self.n_tracks = n_tracks
		self.n_races = n_races

	def lock(self, track_i, step_i):
		return

	def release(self, track_i, step_i):
		return

	def race(self):
		total_run = self.n_tracks * self.n_races

		#Lock first step
		self.lock(track_i = 0, step_i = 0)

		for step_i in range(1, total_run):

			#Lock next
			self.lock(track_i = step_i % self.n_tracks, step_i = step_i)

			#Release previous
			self.release(track_i = (step_i - 1) % self.n_tracks)

		#Final release
		self.release(track_i = step_i % self.n_tracks)

class pylocksfileProcRace(procRace):
	def __init__(self, procIdx, n_tracks, n_races, fpath, writeLock, results_queue):
		super(pylocksfileProcRace, self).__init__(procIdx = procIdx, n_tracks = n_tracks, n_races = n_races)
		self.l = pylocksfile(fpath, verbose = False)
		self.writeLock = writeLock
		self.results_queue = results_queue
		self.procIdx = procIdx

	def lock(self, track_i, step_i):
		self.l.acquire(writeLock = self.writeLock, lock_n = track_i)
		
		#Record the Lock
		self.results_queue.put([self.procIdx, track_i, step_i])
		return

	def release(self, track_i):
		self.l.release(lock_n = track_i)
		return


class pythonLockProcRace(procRace):
	def __init__(self, procIdx, n_tracks, n_races, locks_list, results_queue):
		super(pythonLockProcRace, self).__init__(procIdx = procIdx, n_tracks = n_tracks, n_races = n_races)
		self.locks_list = locks_list
		self.results_queue = results_queue

	def lock(self, track_i, step_i):
		self.locks_list[track_i].acquire()

		#Record the Lock
		self.results_queue.put([self.procIdx, track_i, step_i])
		return

	def release(self, track_i):
		self.locks_list[track_i].release()
		return

def run_pylocksfileProcRace(results_queue, procIdx, n_tracks, n_races, fpath, writeLock):
	join_race = pylocksfileProcRace(procIdx, n_tracks, n_races, fpath, writeLock, results_queue)
	join_race.race()

def run_pythonLockProcRace(locks_list, results_queue, procIdx, n_tracks, n_races):
	join_race = pythonLockProcRace(procIdx, n_tracks, n_races, locks_list, results_queue)
	join_race.race()


def testCorrectness(q, n_process, verbose = True):
	#Create the list of the records
	records = list() 
	while not q.empty():
		records.append(q.get())

	#Iterate over the records from the race. Once for every process
	for currectProcIdx in range(n_process):
		#A list of sets, one for each process. For processes that are ahead and for these behind
		procAhead = set()
		procBehind = set()

		#Record current position of current process
		procCurrentPosition = -1

		for record in records:
			
			procIdx, track_i, step_i = record

			#Correctness within the process
			if currectProcIdx == procIdx:

				#Increment position by 1
				procCurrentPosition += 1
				
				#Check new position is equal to record
				if (step_i) != procCurrentPosition:
					if verbose:
						print(currectProcIdx, "Internal Order Error.")
					return False

				#Continue to next record
				continue

			#Add to the set these behind and these ahead
			if step_i <= procCurrentPosition:
				procBehind.add(procIdx)
			else:
				procAhead.add(procIdx)

		if verbose:
			#Print some info about this process
			print(currectProcIdx, "Done. Processes behind:", procBehind, "Processes Ahead",procAhead)

		#Check procBehind and procAhead intersection is empty
		if procBehind.intersection(procAhead):
			if verbose:
				print(currectProcIdx, "Race Order Error.", procBehind, procAhead)			
			return False

	return True

def testRace(locksfile_path, n_process, n_tracks, n_races):
	print("Running testRace...")

	n_process = n_process

	#n_tracks must be bigger than n_process or we'll get deadlock
	n_tracks = n_tracks
	n_tracks = max(n_tracks, n_process + 1)

	n_races = n_races

	writeLock = True

	pylocksfileProcRaceArgs = list()
	for procIdx in range(n_process):
		pylocksfileProcRaceArgs.append( (procIdx, n_tracks, n_races, locksfile_path, writeLock) )
	

	pool = Pool(n_process)
	m = Manager()
	q = m.Queue()
	func = partial(run_pylocksfileProcRace, q)

	start_time = time.time()
	
	pool.starmap(func, pylocksfileProcRaceArgs)
	pool.close()
	pool.join()

	end_time = time.time()

	pylocksfile_time = end_time - start_time

	print("pylocksfile took", pylocksfile_time)

	if not testCorrectness(q, n_process, verbose = True):
		print("pylocksfile incorrect!\n")
	else:
		print("pylocksfile correct.\n")


	pythonLockProcRaceArgs = list()
	for procIdx in range(n_process):
		pythonLockProcRaceArgs.append( (procIdx, n_tracks, n_races) )

	pool = Pool(n_process)
	m = Manager()
	q = m.Queue()
	#As suggested in https://stackoverflow.com/questions/25557686/python-sharing-a-lock-between-processes
	locks_list = [m.Lock() for i in range(n_tracks)]
	func = partial(run_pythonLockProcRace, locks_list, q)
	
	start_time = time.time()
	
	pool.starmap(func, pythonLockProcRaceArgs)
	pool.close()
	pool.join()
	
	end_time = time.time()
	
	pythonlock_time = end_time - start_time

	print("python locks took", pythonlock_time)

	if not testCorrectness(q, n_process, verbose = True):
		print("python locks incorrect!\n")
	else:
		print("python locks correct.\n")

	print("testRace - Speed-Up ", pythonlock_time / pylocksfile_time)

def testRangesProc1(globalBarrier, locksfile_path):
	#Create pylocksfile
	l = pylocksfile(locksfile_path = locksfile_path, verbose = True, l_id = 'One')

	#Wait for other process to arrive
	globalBarrier.wait()

	#Start the test
	l.acquire(writeLock = True, lock_n = (0, 3))# locking 0,1,2 exclusive
	
	l.acquire(writeLock = False, lock_n = (1, 1))# switching lock 1 to shared
	
	l.release(1)# releasing lock 1
	
	l.acquire(writeLock = True, lock_n = (3, 2))# attemping to lock 3,4 exclusive
	
	l.acquire(writeLock = False, lock_n = (0, 1))# switching lock 0 to read
	
	l.release(0)# releasing lock 0
	
	l.acquire(writeLock = False, lock_n = 3)# switching lock 3 shared

	l.acquire(writeLock = False, lock_n = 0)# attempt to lock 0 shared
	
	l.acquire(writeLock = True, lock_n = (0,6))# attemping to lock 0,1,2,3,4,5 exclusive
	
	l.release()#releasing all
	

def testRangesProc2(globalBarrier, locksfile_path):
	#Create pylocksfile
	l = pylocksfile(locksfile_path = locksfile_path, verbose = True, l_id = 'Two')
		
	#Wait for other process to arrive
	globalBarrier.wait()

	#Start the test
	l.acquire(writeLock = True, lock_n = (3, 3))# locking 3,4,5 exclusive
	
	l.acquire(writeLock = True, lock_n = (1, 1))# attempting to lock 1 exlusive
	
	l.release(4)# release 4
	
	l.release(3)# release 3
	
	l.acquire(writeLock = False, lock_n = 0)# attempting to lock 0 shared
	
	l.acquire(writeLock = True, lock_n = 0)# attempting to lock 0 exclusive
	
	l.release((0,2))# release 0,1
	
	l.release((4,1))# release 4
	
	l.release((3,1))# release 3

	#Two Should release 5 now when exiting scope
	return

def smap(f):
    return f()

def testReadWriteLocks(locksfile_path):
	print("Running testReadWriteLocks...")
	#Using manager only for barrier...
	pool = Pool(2)
	m = Manager()
	b = m.Barrier(2)
	funcs = [partial(testRangesProc1, b, locksfile_path), partial(testRangesProc2, b, locksfile_path)]
	
	pool.map(smap, funcs)
	pool.close()
	pool.join()


def main():
	locksfile_path = './testlock.lock'

	testReadWriteLocks(locksfile_path = locksfile_path)

	print("\n")

	testRace(locksfile_path = locksfile_path, n_process = 4, n_tracks = 50, n_races = 100)
	

if __name__ == '__main__':
	main()
