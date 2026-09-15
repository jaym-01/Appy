# Privacy policy

*Last updated 15 September 2026, for Hudzen 1.0.0.*

Hudzen is a Windows app that lets you browse your iPhone or iPad from File
Explorer over USB. The short version: Hudzen has no accounts, no analytics, and
no servers of its own. Your files and your device's details never leave your
PC. Everything below is a plain description of what the app actually does.

## What Hudzen reads and where it goes

**Files on your device.** Hudzen reads files from the device over the USB cable
and serves them to File Explorer through a small server that runs on your PC
and is only reachable from your PC. A file is only transferred when you open
or copy it, and it only ever goes from the device to your own computer. Hudzen
is read-only, so it cannot change or delete anything on the device. Hudzen does
not keep copies of your files; the copies you make land wherever you put them.

Windows may keep its own thumbnail and file caches for locations you open in
Explorer, as it does for any network folder. That is Windows' behaviour, not
Hudzen's, and Hudzen has no control over it.

**Device details.** To show a device in its list, Hudzen reads the device's name
(for example "Jay's iPhone"), model, iOS version and unique device identifier.
These are held in memory only while the device is plugged in, and are dropped
when it is unplugged or Hudzen closes. They are never written to disk or sent
anywhere.

**Pairing record.** Hudzen works through the trust relationship you set up when
you tap **Trust** on the device. Normally it uses the pairing record that
Apple's own software (the Apple Devices app or iTunes) already keeps on your
PC. If no such record exists, the library Hudzen uses (pymobiledevice3) creates
one and saves it as `%USERPROFILE%\.pymobiledevice3\<device id>.plist`. This
file contains the certificates that identify your PC to your device; treat it
like a key. Deleting that folder removes it, and the device will ask you to
trust the computer again next time.

**Windows settings.** Hudzen reads your accent colour and light/dark theme from
the Windows registry so its window matches the rest of your desktop. It only
reads them.

## The update check

The installed version of Hudzen (from `HudzenSetup.exe`) checks for a newer
release each time it starts. It makes one HTTPS request to GitHub
(`api.github.com`) asking for the latest release of this project. That request
carries what any web request carries, chiefly your IP address, plus a plain
`Hudzen` user-agent string. It contains no information about you or your
devices. How GitHub handles the request is covered by
[GitHub's privacy statement](https://docs.github.com/en/site-policy/privacy-policies/github-general-privacy-statement).

Nothing is downloaded or installed unless you press **Install update**. If you
do, the installer is downloaded from `github.com` into your temporary folder
and run. There is currently no setting to turn the check off. Running Hudzen
from source never checks for updates.

This is the only network connection Hudzen makes.

## What Hudzen does not do

- No accounts, sign-in or registration.
- No analytics, telemetry, usage statistics or crash reporting.
- No advertising.
- No log files written to disk.
- No servers run by the author: the only outside connection is the GitHub
  update check described above.
- Never sends your files, device details or anything else anywhere.

## Other software on your PC

While Hudzen is running and a device is plugged in, that device's files are
available at an address like `\127.0.0.1@2121\root\`. The address is bound to
`127.0.0.1`, so nothing on your network or the internet can reach it. It does
not ask for a password, though, so any program running on this PC could read
files from the device for as long as Hudzen is open. Close Hudzen or unplug the
device when you are done.

## Changes

If Hudzen's behaviour changes, this page will be updated to match, and the
project's git history shows exactly what changed and when.

## Contact

Questions or concerns: open an issue at
<https://github.com/jaym-01/Hudzen/issues>.
