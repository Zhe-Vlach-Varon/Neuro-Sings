# Karaoke Stream Setlist File Format
Specifies the order of songs and other info for a karaoke stream
## Filename
The filename should start with the date in YYYY-mm-dd format, optionally followed by a space and other text to help identify the stream. The file must be a .txt file
## File Content
There are three types of lines in a setlist file
| Line | Notes |
|------|-------|
|Album Info | The first line must be an Album Info line, specifies date, singer, and optional album title and album cover |
| Lead Singer Change | specifies singers for a song |
| Song | lists track nuber, song title, original artist, singer(s), whether it is a new song or a duplicate and optional song cover art |
### Album Info Line
Lists info about the karaoke stream
| Field  | Notes             | Required |
|--------|-------------------|----------|
| Date   | YYYY-mm-dd format | Required |
| Singer | the first singer, the Neuro Twin on the right side of the screen during duet songs, or the only singer in the first solo song| Required |
| Album Title | If ommitted will be set to ```"{singer} {date} Karaoke"``` | Optional |
| Album Cover Art | the filename stem of a image in the custom image folder, if omitted the normal Karaoke Stream Cover Art will be generated, currently must be a jpeg image | Optional (Requires Album Title to be present) |\
<!-- how likely is it to have custom album art without custom album title? -->
Fields are seperated by ```" | "``` a vertical bar (pipe) character with a space on either side (without the quote marks)\
Example: ```2026-01-06 | Neuro | Neuro Subathon 3 VR Karaoke Concert | neuro 3d 2026-01-06```
### Lead Singer Change
Specifies the primary singer, the one on the left in duets, has changed.\
Options are ```Neuro``` or ```Evil```
### Song Entry
Lists info about a song, fields are separated by ```" | "```
| Field | Notes | Required |
|-------|-------|----------|
| Track Number | int | Required |
| Song Title | The full title as given by Unofficial Neuro Karaoke Archive | Required |
| Original Artist | full artist credits as given by Unofficial Neuro Karaoke Archive | Required |
| Singer | Neuro, Evil, Twin-Duet, Collab-Duet(Singers) | Required |
| Is New Song | if a song is a duplicate, there is no new file from the archive | Required |
| Cover Art | custom cover art to use for this song (see Album Cover Art above for details) if omitted falls back to first the Album Cover Art, then the default karaoke stream cover art generation | Optional |