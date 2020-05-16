# pylocksfile

pylocksfile is a simple python package for linux-based systems. This package takes advantage of linux's internal file-system locking mechanism and provided a simple read/write locking interface for inter-process communication.

## Advantages

*pylocksfile* has several advantages over the native python locks:

*	Allow read/write (shared/exclusive) locking mechanising.
*	Significantly smaller over-head for *acquire*/*release* operations.
*	Supports many different locks within a single *pylocksfiles* (hence the **locks** in *pylocksfile*).
*	Interval-based locking mechanising. Supports multiple *acquire*/*release* operations simultaneously, as long as locks indices are consecutive.
*	Locks are shared via linux file-system, so there is no need to pass the lock object upon process creation, any process may share it at any time.
*	Linux provides dead-lock detection, for up to 10 locks dependencies.

## Similar libraries

https://github.com/benediktschmitt/py-filelock library *"which implements a platform independent file lock in Python"*.

## Usage and Examples

```Python
from pylocksfile import pylocksfile

#Create a pylocksfile object. "dataLocksFile.lock" will be the locking file
locksfile = pylocksfile(locksfile_path = "dataLocksFile.lock", verbose = False, l_id = 'process_1')

#Acquiring lock 0 for reading (shared lock) with blocking
locksfile.acquire(writeLock = False, lock_n = 0, blocking = True)

# Do some reading (shared) operation assosiated lock 0.

#Acquiring locks 1,2,3 for writing (exclusive lock) with blocking
locksfile.acquire(writeLock = True, lock_n = (1,3), blocking = True)

# Do some writing (exclusive) operation assosiated locks 1,2,3. 
# Do some reading (shared) operation assosiated lock 0.

#Using 'with' statement. Notice (2,1) means offset of 1 locks from lock 2, hence it is equivalent to 'lock_n = 2'.
with locksfile(writeLock = False, lock_n = (2,1)):
	#Converts lock 2 to read (shared). Do read (shared) operation on 0,2 and write (exclusive) on 1,3
	pass

# Do some writing (exclusive) operation assosiated locks 1,3. 
# Do some reading (shared) operation assosiated lock 0.

#Releasing lock 0.
locksfile.release(lock_n = (0,1))

#Releasing all locks from 3 to 1000
locksfile.release(lock_n = (3,997))

#Release all the locks
locksfile.release()

#End of script. On destruction of pylocksfile object, all remaining locks will be freed.
return
```

## Testing

*test.py* consists of two tests.

*	**testReadWriteLocks(\*args)** test is a simple hard-coded script where two processes block each other at each step. It show general correctness of the locking mechanism,
*	**testRace(\*args)** tests not only the correctness of the locking mechanism, but also it's speed. The test consists of several process performing hand-over-hand iteration
	over a cyclic list several times. *n_process* is the number of processes, *n_tracks* is the length of the list and *n_races* is the number of cycles.
	It show that as *n_tracks* and *n_races* increases, *pylocksfile* is up to 3 times faster than native python locks. As *n_process* increases, and *n_tracks* decreases, 
	the speedup decreases to 1 due to context switch over-head.