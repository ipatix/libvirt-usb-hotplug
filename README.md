## libvirt-usb-hotplug

This project contains one simple script to automatically attach or detach USB device to/from a libvirt VM.
I was not satisfied with other solutions like [hotplugger](https://github.com/darkguy2008/hotplugger) (buggy, didn't work at all, required odd config, etc.).
Specify your desired USB ports and any device plugged into them will automatically be attached to the VM.

However, this project is inspired by hotplugger and does more or less the same thing.
It only works for libvirt which greatly simplifies a few things.
Standalone QEMU is not supported!

### How it works

Like hotplugger, this script is registered as udev run script whenever a USB device is added or removed.
If such an event occurs, the script searches through its config file to find if the current udev event is supposed to be handled or ignored.
A udev event is handled if there is any domain that has a matching USB port assigned.

This allows to passthrough USB devices to a VM without the limitation of matching soley on vendor/product ID.
For example, when you want to plug in two keyboards or mice of the same type (which I happen to have a lot of) to different VMs, it would otherwise be impossible due to the vendor/product IDs being identical.
It is achieved by using libvirt's mechanism to specify the device via bus and id number which are unique per connected device.
The required XML is generated on the fly and passed over to `virsh`.

### How to set up

Download `libvirt-usb-hotplug.py` to any desired location and open it in a text editor.
I preferred to have as few files as possible, so the configuration is directly inside the python script.
It looks something like this:

```python
config = [
    (
        "vm1", [
            "/devices/pci0000:00/0000:00:14.0/usb3/3-11",
            "/devices/pci0000:00/0000:00:14.0/usb3/3-10.2",
        ]
    ), (
        "test-windows-vm2", [
            "/devices/pci0000:00/0000:00:14.0/usb3/3-12",
        ]
    ),
]
```

In this example you can two libvirt domains being configured.
The first one called `vm1` has two USB ports which are monitored by this script: Port 11 on Bus 3, and Port 10 ("sub-port" 2) on Bus 3.
If you have a USB hub connected to your computer, it is possible to also selectively monitor specific ports of that, like previously described as "subport" and they are identified with a `.ID` suffix.
This may not work with all USB hubs as I've heard rumors about the existance of some really dumb ones which are entirely transparent to the host.
I should also emphasize that you don't have to explicitly specify every single sub port of your USB hub incase you have one.
Just specifying the primary port that you want to pass through should be enough.

The second VM "test-windows-vm2" in this example only has one port configured.

To get the port description string of your USB port, run `udevadm monitor` and plug in (or unplug) your device:

```
UDEV  [11884.167950] xxxx     /devices/pci0000:00/0000:00:14.0/usb3/3-1/3-1.3 (usb)
```

You will get a lot of output but look out for lines like the one above where you only get the device string up to the port description.
The example above shows a device being plugged in over a USB hub to the motherboard.
Without USB hub it will probably look more like this:

```
UDEV  [12018.100916] xxxx     /devices/pci0000:00/0000:00:14.0/usb3/3-2 (usb)
```

Copy the device path into the array that follow the identifier of your libvirt domain (e.g. "vm1" here): ` /devices/pci0000:00/0000:00:14.0/usb3/3-2`.

You can also quickly identify the USB port numbers by running `lsusb -t`:

```
/:  Bus 04.Port 1: Dev 1, Class=root_hub, Driver=xhci_hcd/6p, 5000M
/:  Bus 03.Port 1: Dev 1, Class=root_hub, Driver=xhci_hcd/15p, 480M
    |__ Port 1: Dev 60, If 0, Class=Hub, Driver=hub/4p, 12M
        |__ Port 2: Dev 62, If 0, Class=Human Interface Device, Driver=usbhid, 1.5M
        |__ Port 3: Dev 63, If 0, Class=Human Interface Device, Driver=usbhid, 1.5M
        |__ Port 3: Dev 63, If 1, Class=Human Interface Device, Driver=, 1.5M
        |__ Port 1: Dev 61, If 0, Class=Human Interface Device, Driver=usbhid, 12M
        |__ Port 1: Dev 61, If 1, Class=Human Interface Device, Driver=usbhid, 12M
    |__ Port 14: Dev 5, If 0, Class=Hub, Driver=hub/4p, 480M
        |__ Port 1: Dev 8, If 0, Class=Human Interface Device, Driver=usbhid, 1.5M
        |__ Port 1: Dev 8, If 1, Class=Human Interface Device, Driver=usbhid, 1.5M
/:  Bus 02.Port 1: Dev 1, Class=root_hub, Driver=ehci-pci/2p, 480M
    |__ Port 1: Dev 2, If 0, Class=Hub, Driver=hub/8p, 480M
/:  Bus 01.Port 1: Dev 1, Class=root_hub, Driver=ehci-pci/2p, 480M
    |__ Port 1: Dev 2, If 0, Class=Hub, Driver=hub/6p, 480M
```

Please keep in mind that you will have to repeat this procedure a second time if you intend to pass through both 2.0 and 3.0 devices
since your devices will appear on a different root hub (thus a different bus) when running at a different speed.

Now that your script is successfully configured, we have to register the udev handler.
To do so, create a file in `/etc/udev/rules.d/99-libvirt-usb.rules` with the following content:

```
SUBSYSTEM=="usb", ACTION=="add", RUN+="/path/to/libvirt-usb-hotplug.py"
SUBSYSTEM=="usb", ACTION=="remove", RUN+="/path/to/libvirt-usb-hotplug.py"
```

Usually udev should apply changes to this file automatically, but in case it does not, run `udevadm trigger` afterwards.

After that you're done and devices should automatically be plugged into your VM.

### Information about USB hubs

Although as mentioned above, it is possible to pass through an entire USB hub, the script tries to avoid passing through the actual USB hub itself.
Trying to do so apparently makes all attached devices on the hub disappear and the VM guest fails to enumerate the devices.
Therefore the script tries to avoid passing through the hub device itself by matching various environment variables passed over by udev.
This is likely to be not very stable so I can't guarantee reliable results with using USB hubs.
At the moment the detection works by checking if `ID_MODEL` or `ID_MODEL_FROM_DATABASE` contain the string "hub".
