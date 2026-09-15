# Usage

## Connecting a device

1. Plug the iPhone or iPad in over USB.
2. Unlock it. If it asks **Trust This Computer?**, tap **Trust**.
3. Open Hudzen. The device appears in the list within a couple of seconds.
4. Press **Open in File Explorer**.

Explorer opens at the top of the device's media folder. Browse, open, and
copy files exactly as you would from any other folder: thumbnails, the
preview pane, drag-and-drop, and search all work.

Multiple devices can be plugged in at once; each gets its own row and its own
Explorer location.

## What you see

Hudzen shows the device's media storage, the same area iTunes and Finder expose:

| Folder                         | Contents                                                                  |
| ------------------------------ | ------------------------------------------------------------------------- |
| `DCIM/100APPLE`, `101APPLE`, … | Camera roll photos and videos, with their real filenames (`IMG_5019.JPG`) |
| `Downloads`                    | Files saved from Safari                                                   |
| `Books`                        | Books and PDFs                                                            |
| others                         | Depends on the apps installed                                             |

Photos-database internals (`PhotoData`, `MediaAnalysis`, `iTunes_Control`,
`Purchases`) and dot-files are hidden.

App sandboxes and system files are not accessible. That is a limit of the
protocol.

## Read-only

Nothing can be written to, renamed on, or deleted from the device through
Hudzen. Explorer will refuse any such operation. Viewing and copying files **off** the device is the only direction supported.

## The address

The button opens a UNC path of the form:

```
\\127.0.0.1@2121\root\
```

Hover the button to see it. You can paste it into Explorer's address bar, a
file dialog, or any other program that accepts network paths. The port is
`2121` for the first device, `2122` for the second, and so on.

The address is only valid while Hudzen is running and the device is plugged in.
It binds to `127.0.0.1`, so nothing outside this machine can reach it.

## Disconnecting

Unplug the device or close Hudzen. Either stops the server; Explorer windows
pointing at it will show an error on their next refresh, which is expected.

If the device auto-locks mid-transfer, Hudzen reconnects automatically. A brief
pause is normal.
