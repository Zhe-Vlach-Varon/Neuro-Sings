# Karaoke Stream Setlist File Format
Specifies the order of songs and other info for a karaoke stream
## Filename
The filename should start with the date in YYYY-mm-dd format, optionally followed by a space and other text to help identify the stream. The file may have any text file type, the files are similar to csv (pipe) files, but because of the inclusion of comments, and not having a fixed number of fields on all lines I chose to make them .txt files
## File Content
There are three types of lines in a setlist file
| Line | Notes |
|------|-------|
|Album Info | The first line must be an Album Info line, specifies date, singer, and optional album title and album cover |
| Lead Singer Change | specifies lead singer for the following block of songs |
| Song | lists track nuber, song title, original artist, singer(s), whether it is a new song or a duplicate and optional song cover art |
| Comment or other line not to process | Start a line with two exclamation points `!!` to tell the setlist parser not to parse this line |
### Album Info Line
Lists info about the karaoke stream
| Field  | Notes             | Required |
|--------|-------------------|----------|
| Date   | YYYY-mm-dd format | Required |
| Singer | the first singer, the Neuro Twin on the right side of the screen during duet songs, or the only singer in the first solo song| Required |
| Album Title | If ommitted will be set to ```"{singer} {date} Karaoke"``` | Optional |
| Album Cover Art | the filename stem of a image in the custom image folder, if omitted the normal Karaoke Stream Cover Art will be generated, currently must be a jpeg image | Optional |\
<!-- how likely is it to have custom album art without custom album title? -->
Fields are seperated by `|` a vertical bar (pipe) character with optional spaces on either side to make it more readable\
Example: ```2026-01-06 | Neuro | Neuro Subathon 3 VR Karaoke Concert | neuro 3d 2026-01-06```\
If you ommit a field, you still need to put a `|` to mark where it would be if you include later fields

If a Setlist spans multiple dates, an additional album info line with the new date is needed, and all album info lines need to have the same custom album title in order to be grouped together correctly (besides Januray-March 2023 Stream Covers which are treated specially)
### Lead Singer Change
Specifies the primary singer, the one on the left in duets, has changed.\
Options are ```Neuro``` or ```Evil```

#### Outfit and Microphones TO BE IMPLEMENTED will probably replace Lead Singer Change

| Field | Notes | required |
|-------|-------|----------|
| Right Singer | The singer on the right | Required |
| Right Outfit | what outfit (v1, v2, v2 Pirate, v2 clown, v3, etc) | Required |
| Right Microphone | what mic (None, Pink, Red, Evil's Custom, Neuro's Custom, etc) | Required |
| Left Singer | second singer in duet | Optional |
| Left Outfit | same as right outfit | Optional |
| Left Microphone | same as right mic | Optional |


### Song Entry
Lists info about a song, fields are separated by `|`
| Field | Notes | Required |
|-------|-------|----------|
| Track Number | int | Required |
| Song Title | The full title as given by Unofficial Neuro Karaoke Archive | Required |
| Original Artist | full artist credits as given by Unofficial Neuro Karaoke Archive | Required |
| Singer | Neuro, Evil, Twin-Duet, Collab-Duet(Singers) defaults to Album Lead Singer | Optional |
| Is New Song | if a song is a duplicate, there is no new file from the archive | Required |
| Cover Art | custom cover art to use for this song (see Album Cover Art above for details) if omitted falls back to first the Album Cover Art, then the default karaoke stream cover art generation | Optional |
| Additional Flags | additional flags to be added to the song record in the database, can be anything you might want to filter by, as long as each flag is followed by a `;` with no spaces before or after | Optional
<!-- automate detection of new songs vs duplicates -->