# Dist

Download the packaged app from this folder. `latest.spl` is always the current build. The versioned file is the same package with the version in the name.

| File | What it is |
| --- | --- |
| [latest.spl](latest.spl) | Current Splunk Health Derek+ Cloud package |
| [splunk_exec_health-1.7.88.spl](splunk_exec_health-1.7.88.spl) | Same package, versioned name |

Install: **Apps → Manage apps → Install app from file**, then upload the `.spl`.

Older local builds stay on the machine that ran `bash tools/package.sh`. Only the current `.spl` is kept in git.
