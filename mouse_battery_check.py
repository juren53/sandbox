#!/usr/bin/env python3
"""
Wireless Mouse Battery Checker
Attempts to detect and read battery information from HID devices
"""

import hidapi as hid
import sys
import time

def list_hid_devices():
    """List all HID devices on the system"""
    print("Available HID devices:")
    print("-" * 60)
    devices = hid.enumerate()
    mouse_devices = []
    
    for device in devices:
        vendor_id = device.vendor_id
        product_id = device.product_id
        manufacturer = device.manufacturer_string or 'Unknown'
        product = device.product_string or 'Unknown'
        path = device.path
        
        print(f"VID: 0x{vendor_id:04x}, PID: 0x{product_id:04x}")
        print(f"  Manufacturer: {manufacturer}")
        print(f"  Product: {product}")
        print(f"  Path: {path.decode('utf-8') if isinstance(path, bytes) else path}")
        
        # Check if this looks like a mouse
        if ('mouse' in product.lower() or 
            'receiver' in product.lower() or
            vendor_id == 0x32c2):  # Your mouse's vendor ID
            mouse_devices.append(device)
            print("  ** POTENTIAL MOUSE DEVICE **")
        print()
    
    return mouse_devices

def try_read_battery(device_info):
    """Attempt to read battery information from a device"""
    vendor_id = device_info.vendor_id
    product_id = device_info.product_id
    path = device_info.path
    
    print(f"Attempting to read battery from device:")
    print(f"  VID: 0x{vendor_id:04x}, PID: 0x{product_id:04x}")
    print(f"  Product: {device_info.product_string or 'Unknown'}")
    
    try:
        # Try to open the device
        device = hid.Device(vendor_id=vendor_id, product_id=product_id)
        
        print(f"  Device opened successfully!")
        
        # Get device info
        manufacturer = device.get_manufacturer_string()
        product = device.get_product_string()
        serial = device.get_serial_number_string()
        
        print(f"  Manufacturer: {manufacturer}")
        print(f"  Product: {product}")
        print(f"  Serial: {serial}")
        
        # Try common battery report IDs
        battery_report_ids = [0x01, 0x02, 0x03, 0x07, 0x20, 0x21]
        
        for report_id in battery_report_ids:
            try:
                print(f"  Trying report ID: 0x{report_id:02x}")
                
                # Try to get a feature report (common for battery info)
                data = device.get_feature_report(report_id, 64)
                if data and len(data) > 1:
                    print(f"    Got data: {[hex(x) for x in data[:8]]}")
                    
                    # Look for potential battery values
                    for i, byte in enumerate(data[1:8]):  # Skip report ID
                        if 0 <= byte <= 100:  # Potential battery percentage
                            print(f"    Potential battery at byte {i+1}: {byte}%")
                
            except Exception as e:
                # This is expected for unsupported report IDs
                pass
        
        # Try reading input reports
        print("  Trying to read input reports...")
        device.set_nonblocking(True)
        
        for i in range(5):  # Try 5 times
            try:
                data = device.read(64, timeout_ms=1000)
                if data:
                    print(f"    Input report {i+1}: {[hex(x) for x in data[:8]]}")
            except Exception as e:
                break
        
        device.close()
        return True
        
    except Exception as e:
        print(f"  Error: {e}")
        return False

def main():
    print("Wireless Mouse Battery Checker")
    print("=" * 50)
    
    # List all HID devices
    mouse_devices = list_hid_devices()
    
    if not mouse_devices:
        print("No potential mouse devices found!")
        print("\nNote: Your mouse might not support battery reporting,")
        print("or it might not be recognized as a mouse by the HID subsystem.")
        return
    
    print(f"\nFound {len(mouse_devices)} potential mouse device(s)")
    print("=" * 50)
    
    # Try to read battery from each potential mouse device
    for i, device in enumerate(mouse_devices):
        print(f"\nTesting device {i+1}/{len(mouse_devices)}:")
        print("-" * 30)
        success = try_read_battery(device)
        
        if not success:
            print("  Could not read battery information from this device")

if __name__ == "__main__":
    main()
