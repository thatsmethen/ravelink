use super::*;
use core::mem::{offset_of, size_of};
use std::{
    alloc::{GlobalAlloc, Layout, System},
    cell::Cell,
};

thread_local! {
    static TRACK_ALLOCATIONS: Cell<bool> = const { Cell::new(false) };
    static ALLOCATIONS: Cell<usize> = const { Cell::new(0) };
}
struct CountingAllocator;
unsafe impl GlobalAlloc for CountingAllocator {
    unsafe fn alloc(&self, layout: Layout) -> *mut u8 {
        if TRACK_ALLOCATIONS.try_with(Cell::get).unwrap_or(false) {
            ALLOCATIONS.with(|n| n.set(n.get() + 1));
        }
        System.alloc(layout)
    }
    unsafe fn dealloc(&self, p: *mut u8, layout: Layout) {
        System.dealloc(p, layout)
    }
    unsafe fn realloc(&self, p: *mut u8, layout: Layout, size: usize) -> *mut u8 {
        if TRACK_ALLOCATIONS.try_with(Cell::get).unwrap_or(false) {
            ALLOCATIONS.with(|n| n.set(n.get() + 1));
        }
        System.realloc(p, layout, size)
    }
}
#[global_allocator]
static ALLOCATOR: CountingAllocator = CountingAllocator;

unsafe extern "C" fn changed(_: HostRef, _: ObjectId, _: u32, _: *const Address) -> Status {
    OK
}
unsafe extern "C" fn copy(_: HostRef, _: CfRef, _: *mut CfRef) -> Status {
    UNSUPPORTED
}
unsafe extern "C" fn write(_: HostRef, _: CfRef, _: CfRef) -> Status {
    UNSUPPORTED
}
unsafe extern "C" fn delete(_: HostRef, _: CfRef) -> Status {
    UNSUPPORTED
}
unsafe extern "C" fn request(_: HostRef, _: ObjectId, _: u64, _: *mut c_void) -> Status {
    UNSUPPORTED
}
static TEST_HOST: HostInterface = HostInterface {
    properties_changed: changed,
    copy_from_storage: copy,
    write_to_storage: write,
    delete_from_storage: delete,
    request_configuration: request,
};

fn address(selector: &[u8; 4], scope: u32) -> Address {
    Address {
        selector: code(selector),
        scope,
        element: 0,
    }
}

#[test]
fn sdk_64_bit_layout() {
    assert_eq!(size_of::<DriverInterface>(), 23 * 8);
    assert_eq!(size_of::<HostInterface>(), 5 * 8);
    assert_eq!(size_of::<ClientInfo>(), 24);
    assert_eq!(size_of::<TimeStamp>(), 64);
    assert_eq!(size_of::<CycleInfo>(), 224);
    assert_eq!(size_of::<Format>(), 40);
    assert_eq!(size_of::<RangedFormat>(), 56);
    assert_eq!(size_of::<Uuid>(), 16);
    assert_eq!(offset_of!(DriverInterface, do_io), 21 * 8);
    assert_eq!(offset_of!(CycleInfo, input), 80);
    assert_eq!(offset_of!(CycleInfo, output), 144);
}

#[test]
fn direct_vtable_properties_reject_bad_inputs_and_validate_formats() {
    unsafe {
        let driver = driver_ref();
        let v = &**driver;
        let mut result = ptr::null_mut();
        assert_eq!(
            (v.query_interface)(driver.cast(), DRIVER_UUID, &mut result),
            OK
        );
        assert_eq!(result, driver.cast());
        assert_ne!(
            (v.query_interface)(driver.cast(), TYPE_UUID, &mut result),
            OK
        );
        assert!(result.is_null());
        assert_eq!(
            (v.has_property)(driver, 9999, 0, &address(b"lnam", GLOBAL)),
            0
        );
        assert_eq!(
            (v.has_property)(driver, 100, 0, &address(b"nsrt", INPUT)),
            0
        );
        assert_eq!((v.has_property)(driver, 100, 0, ptr::null()), 0);
        let mut bytes = 999;
        let mut result = 0u32;
        let list = address(b"dev#", GLOBAL);
        assert_eq!(
            (v.get_property)(
                driver,
                PLUGIN,
                0,
                &list,
                0,
                ptr::null(),
                3,
                &mut bytes,
                (&mut result as *mut u32).cast()
            ),
            BAD_SIZE
        );
        assert_eq!(bytes, 0);
        assert_eq!(
            (v.get_property)(
                driver,
                PLUGIN,
                0,
                &list,
                0,
                ptr::null(),
                4,
                &mut bytes,
                (&mut result as *mut u32).cast()
            ),
            OK
        );
        assert_eq!((result, bytes), (100, 4));
        let mut raw = [0u8; 42];
        let format = address(b"sfmt", GLOBAL);
        assert_eq!(
            (v.get_property)(
                driver,
                101,
                0,
                &format,
                0,
                ptr::null(),
                40,
                &mut bytes,
                raw.as_mut_ptr().add(1).cast()
            ),
            OK
        );
        assert_eq!(
            ptr::read_unaligned(raw.as_ptr().add(1).cast::<Format>()),
            FORMAT
        );
        let mut malformed = FORMAT;
        malformed.channels = 1;
        assert_eq!(
            (v.set_property)(
                driver,
                101,
                0,
                &format,
                0,
                ptr::null(),
                40,
                (&malformed as *const Format).cast()
            ),
            BAD_FORMAT
        );
        assert_eq!(
            (v.set_property)(
                driver,
                101,
                0,
                &format,
                0,
                ptr::null(),
                40,
                (&FORMAT as *const Format).cast()
            ),
            OK
        );
        assert_eq!(
            (v.set_property)(
                driver,
                101,
                0,
                &format,
                0,
                ptr::null(),
                39,
                (&FORMAT as *const Format).cast()
            ),
            BAD_SIZE
        );
        let wrong_class = code(b"adev");
        let owned = address(b"ownd", GLOBAL);
        assert_eq!(
            (v.get_property_size)(
                driver,
                100,
                0,
                &owned,
                4,
                (&wrong_class as *const u32).cast(),
                &mut bytes
            ),
            OK
        );
        assert_eq!(bytes, 0);
    }
}

#[test]
fn direct_host_lifecycle_audio_clock_and_allocation_contract() {
    unsafe {
        let driver = driver_ref();
        let v = &**driver;
        assert_eq!((v.initialize)(driver, &TEST_HOST), OK);
        let client = ClientInfo {
            id: 601,
            process_id: 0,
            native_endian: 1,
            bundle_id: ptr::null(),
        };
        assert_eq!((v.add_client)(driver, 100, &client), OK);
        assert_eq!((v.start_io)(driver, 100, 601), OK);
        let mut cycle = CycleInfo::default();
        cycle.output.sample_time = 1000.0;
        cycle.output.flags = 1;
        cycle.input.sample_time = 1512.0;
        cycle.input.flags = 1;
        let mut source = [0.25f32, -0.25, 0.5, -0.5, 0.75, -0.75, 1.0, -1.0];
        let mut destination = [99.0f32; 8];
        let mut sample = 0.0;
        let mut host = 0;
        let mut seed = 0;
        ALLOCATIONS.with(|n| n.set(0));
        TRACK_ALLOCATIONS.with(|b| b.set(true));
        let write_status = (v.do_io)(
            driver,
            100,
            102,
            601,
            WRITE,
            4,
            &cycle,
            source.as_mut_ptr().cast(),
            ptr::null_mut(),
        );
        let read_status = (v.do_io)(
            driver,
            100,
            101,
            601,
            READ,
            4,
            &cycle,
            destination.as_mut_ptr().cast(),
            ptr::null_mut(),
        );
        let time_status = (v.zero_timestamp)(driver, 100, 601, &mut sample, &mut host, &mut seed);
        TRACK_ALLOCATIONS.with(|b| b.set(false));
        assert_eq!(ALLOCATIONS.with(Cell::get), 0);
        assert_eq!((write_status, read_status, time_status), (OK, OK, OK));
        assert_eq!(destination, source);
        assert_eq!(seed, 1);
        assert!(host <= mach_absolute_time());
        assert_eq!(
            (v.do_io)(
                driver,
                100,
                102,
                601,
                READ,
                4,
                &cycle,
                destination.as_mut_ptr().cast(),
                ptr::null_mut()
            ),
            BAD_STREAM
        );
        assert_eq!(
            (v.do_io)(
                driver,
                100,
                101,
                601,
                READ,
                8193,
                &cycle,
                destination.as_mut_ptr().cast(),
                ptr::null_mut()
            ),
            ILLEGAL
        );
        cycle.input.sample_time = 2000.0;
        assert_eq!(
            (v.do_io)(
                driver,
                100,
                101,
                601,
                READ,
                4,
                &cycle,
                destination.as_mut_ptr().cast(),
                ptr::null_mut()
            ),
            OK
        );
        assert_eq!(destination, [0.0; 8]);
        cycle.input.sample_time = f64::NAN;
        assert_eq!(
            (v.do_io)(
                driver,
                100,
                101,
                601,
                READ,
                4,
                &cycle,
                destination.as_mut_ptr().cast(),
                ptr::null_mut()
            ),
            ILLEGAL
        );
        assert_eq!((v.stop_io)(driver, 100, 601), OK);
        assert_eq!((v.stop_io)(driver, 100, 601), ILLEGAL);
        assert_eq!((v.remove_client)(driver, 100, &client), OK);
    }
}
