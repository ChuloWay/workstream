//! One atomic node reservation for a checker and its sequential child trials.
use std::sync::{
    atomic::{AtomicBool, Ordering},
    Arc, Mutex,
};

#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub(crate) struct Capacity {
    pub(crate) slots: usize,
    pub(crate) memory_bytes: u64,
    pub(crate) storage_bytes: u64,
}

impl Capacity {
    fn checked_add(self, other: Self) -> Option<Self> {
        Some(Self {
            slots: self.slots.checked_add(other.slots)?,
            memory_bytes: self.memory_bytes.checked_add(other.memory_bytes)?,
            storage_bytes: self.storage_bytes.checked_add(other.storage_bytes)?,
        })
    }

    fn fits(self, maximum: Self) -> bool {
        self.slots <= maximum.slots
            && self.memory_bytes <= maximum.memory_bytes
            && self.storage_bytes <= maximum.storage_bytes
    }
}

#[derive(Debug)]
pub(crate) struct Admission {
    used: Mutex<Capacity>,
    maximum: Capacity,
    pub(crate) epoch: String,
    poisoned: AtomicBool,
}

impl Admission {
    pub(crate) fn quarantine(&self) {
        self.poisoned.store(true, Ordering::SeqCst);
    }

    pub(crate) fn reserved_storage_bytes(&self) -> Result<u64, String> {
        let used = self.used.lock().map_err(|_| "node admission unavailable")?;
        if self.poisoned.load(Ordering::SeqCst) {
            return Err("node admission quarantined".into());
        }
        Ok(used.storage_bytes)
    }

    pub(crate) fn new(maximum: Capacity, epoch: String) -> Result<Self, String> {
        if maximum.slots == 0 || maximum.memory_bytes == 0 || maximum.storage_bytes == 0 {
            return Err("node capacity must be bounded".into());
        }
        Ok(Self {
            used: Mutex::new(Capacity::default()),
            maximum,
            epoch,
            poisoned: AtomicBool::new(false),
        })
    }

    pub(crate) fn reserve(
        self: &Arc<Self>,
        outer: Capacity,
        child: Option<Capacity>,
    ) -> Result<Arc<Reservation>, String> {
        if outer.slots != 1
            || outer.memory_bytes == 0
            || outer.storage_bytes == 0
            || child.is_some_and(|c| c.slots != 1 || c.memory_bytes == 0 || c.storage_bytes == 0)
        {
            return Err("invalid invocation capacity".into());
        }
        let charge = outer
            .checked_add(child.unwrap_or_default())
            .ok_or("capacity overflow")?;
        let mut used = self.used.lock().map_err(|_| "node admission unavailable")?;
        if self.poisoned.load(Ordering::SeqCst) {
            return Err("node admission quarantined".into());
        }
        let next = used
            .checked_add(charge)
            .filter(|v| v.fits(self.maximum))
            .ok_or("capacity unavailable")?;
        *used = next;
        Ok(Arc::new(Reservation {
            admission: self.clone(),
            charge,
            child,
            child_active: AtomicBool::new(false),
        }))
    }
}

#[derive(Debug)]
pub(crate) struct Reservation {
    pub(crate) admission: Arc<Admission>,
    charge: Capacity,
    child: Option<Capacity>,
    child_active: AtomicBool,
}

impl Reservation {
    /// Consume reserved child capacity without another global admission wait.
    pub(crate) fn child(self: &Arc<Self>, demand: Capacity) -> Result<ChildReservation, String> {
        let limit = self.child.ok_or("trial capacity was not reserved")?;
        if demand.slots != 1
            || demand.memory_bytes == 0
            || demand.storage_bytes == 0
            || !demand.fits(limit)
        {
            return Err("child exceeds reserved capacity".into());
        }
        let _used = self
            .admission
            .used
            .lock()
            .map_err(|_| "node admission unavailable")?;
        if self.admission.poisoned.load(Ordering::SeqCst) {
            return Err("node admission quarantined".into());
        }
        self.child_active
            .compare_exchange(false, true, Ordering::SeqCst, Ordering::SeqCst)
            .map_err(|_| "child capacity already in use")?;
        Ok(ChildReservation {
            parent: self.clone(),
        })
    }
}

impl Drop for Reservation {
    fn drop(&mut self) {
        // Poisoned admission remains closed; never invent capacity after a panic.
        if let Ok(mut used) = self.admission.used.lock() {
            used.slots -= self.charge.slots;
            used.memory_bytes -= self.charge.memory_bytes;
            used.storage_bytes -= self.charge.storage_bytes;
        }
    }
}

#[derive(Debug)]
pub(crate) struct ChildReservation {
    parent: Arc<Reservation>,
}

impl ChildReservation {
    /// Keep the full invocation charge and reject new work after uncertain cleanup.
    pub(crate) fn quarantine(self) {
        self.parent.admission.quarantine();
        std::mem::forget(self);
    }
}

impl Drop for ChildReservation {
    fn drop(&mut self) {
        self.parent.child_active.store(false, Ordering::SeqCst);
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::Barrier;

    fn amount(slots: usize, memory_bytes: u64, storage_bytes: u64) -> Capacity {
        Capacity {
            slots,
            memory_bytes,
            storage_bytes,
        }
    }

    #[test]
    fn one_slot_node_refuses_trial_before_reserving_outer() {
        let node = Arc::new(Admission::new(amount(1, 200, 200), "test".into()).unwrap());
        assert!(node
            .reserve(amount(1, 10, 10), Some(amount(1, 10, 10)))
            .is_err());
        assert!(node.reserve(amount(1, 10, 10), None).is_ok());
    }

    #[test]
    fn every_limit_is_atomic_and_failed_admission_leaks_nothing() {
        for limit in [amount(1, 200, 200), amount(2, 19, 200), amount(2, 200, 19)] {
            let node = Arc::new(Admission::new(limit, "test".into()).unwrap());
            assert!(node
                .reserve(amount(1, 10, 10), Some(amount(1, 10, 10)))
                .is_err());
            assert_eq!(*node.used.lock().unwrap(), Capacity::default());
        }
    }

    #[test]
    fn child_keeps_peak_reservation_alive_and_is_exclusive() {
        let node = Arc::new(Admission::new(amount(2, 20, 20), "test".into()).unwrap());
        let held = node
            .reserve(amount(1, 10, 10), Some(amount(1, 10, 10)))
            .unwrap();
        assert!(held.child(amount(1, 11, 10)).is_err());
        let child = held.child(amount(1, 10, 10)).unwrap();
        assert!(held.child(amount(1, 10, 10)).is_err());
        drop(held);
        assert!(node.reserve(amount(1, 1, 1), None).is_err());
        drop(child);
        assert_eq!(*node.used.lock().unwrap(), Capacity::default());
        assert!(node.reserve(amount(1, 10, 10), None).is_ok());
    }

    #[test]
    fn competing_invocations_cannot_split_peak_capacity() {
        let node = Arc::new(Admission::new(amount(2, 20, 20), "test".into()).unwrap());
        let barrier = Arc::new(Barrier::new(3));
        let workers: Vec<_> = (0..2)
            .map(|_| {
                let node = node.clone();
                let barrier = barrier.clone();
                std::thread::spawn(move || {
                    barrier.wait();
                    let held = node.reserve(amount(1, 10, 10), Some(amount(1, 10, 10)));
                    barrier.wait();
                    held
                })
            })
            .collect();
        barrier.wait();
        barrier.wait();
        let held: Vec<_> = workers.into_iter().map(|w| w.join().unwrap()).collect();
        assert_eq!(held.iter().filter(|v| v.is_ok()).count(), 1);
        drop(held);
        assert_eq!(*node.used.lock().unwrap(), Capacity::default());
    }

    #[test]
    fn unsettled_child_quarantines_the_node_until_restart() {
        let node = Arc::new(Admission::new(amount(2, 20, 20), "test".into()).unwrap());
        let held = node
            .reserve(amount(1, 10, 10), Some(amount(1, 10, 10)))
            .unwrap();
        held.child(amount(1, 10, 10)).unwrap().quarantine();
        drop(held);
        assert!(node.reserve(amount(1, 1, 1), None).is_err());
        assert!(node.reserved_storage_bytes().is_err());
        assert_eq!(node.used.lock().unwrap().storage_bytes, 20);
    }

    #[test]
    fn uncertain_scratch_cleanup_closes_admission_after_credit_release() {
        let node = Arc::new(Admission::new(amount(2, 20, 20), "test".into()).unwrap());
        let held = node
            .reserve(amount(1, 10, 10), Some(amount(1, 10, 10)))
            .unwrap();
        node.quarantine();
        drop(held);
        assert_eq!(*node.used.lock().unwrap(), Capacity::default());
        assert!(node.reserve(amount(1, 1, 1), None).is_err());
        assert!(node.reserved_storage_bytes().is_err());
    }
}
