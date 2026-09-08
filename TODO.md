# TODO

## Current Plans

- [x] take list of songs from a file, and auto detect duplicates based on presence of file in list of new files
- [x] make it so that the officially released songs will be skipped if not present
  - [x] generate place-holder text files, and include the cover art in a folder with the name of the mp3 file that would have been made for officially released songs
- [x] switch to hashing audio data instead of whole file
  - [x] switch to checking for song presence in DB based on hash of audio data instead of file hash
  - [ ] detect when file metadata doesn't match the database and print a list of issues
  - [x] when generating songs, create a dictionary mapping audio hashes to file names
- [ ] Update cover image generation system
  - [x] add system to handle split karaoke streams like the 2025 Christmas Karaoke (by split I mean one twin did first half, and the other twin did the second half)
  - [ ] add configurable base image sources
    - [ ] add more background images
      - [ ] Christmas 2025 cover
      - [ ] Neuro Background Images
        - [ ] Neuro v1
        - [ ] Neuro v2
        - [ ] Neuro v3 Long Hair Old Mic
        - [ ] Neuro v3 Long Hair New Mic
        - [ ] Neuro v3 Hair Loops Old Mic ??
          - [ ] check when Neuro got her new hairstyle and when she got her new Mic
        - [ ] Neuro v3 Long Hair New Mic
        - [ ] Neuro v3 Hair Loops New Mic
        - [ ] Neuro v3 Cyber Princess Outfit (has there been a karaoke with this outfit?)
        - [ ] Neuro v3 3D
      - [ ] Evil Background Images
        - [ ] Evil v3 Guitar
          - [ ] was their a Evil v2 Guitar?
        - [ ] Evil early Neuro Recolors ??
        - [ ] Evil v2
        - [ ] Evil v3
      - [ ] Duet Backgrounds
        - [ ] Neuro on right
        - [ ] Evil on right
        - [ ] Both twins v2 Models
          - [ ] Sometimes only one twin would have a Mic
        - [ ] Neuro v3 Evil v2
        - [ ] Both twins v3 Models
          - [ ] Evil New Mic Neuro Old Mic
          - [ ] Both twins New Mics
  - [x] fix image system so that "as_drive" flag will tell it to take the default cover image for the song's date
  - [ ] add support for more image file types (e.g. webp, tiff)
- [ ] add support for more input audio types (e.g. .wav)
- [ ] Add more error checking
  - [ ] Check for and remove empty rows in DB/CSV
  - [ ] Check for and handle fields that are empty string instead of Null
- [ ] Add Debug Mode logger statements for easier debugging when something goes wrong
- [ ] update Songlist.md
- [ ] find and add credits for new cover arts
- [ ] check and update database
- [~] fix tagging of albums so songs are grouped correctly in media players that expect all songs in an album to be tagged a certain way (TALB/TPE2 set; still need to handle full-duet-stream flag stripping)
- [~] for generate albums, consider adding track numbers to start of file name (numberedFiles support exists in file_name() but is not enabled in generate_albums)
- [x] generate zvv sort and original sort presets separately (both sorts exist in config.toml; needs preset grouping functionality for completeness)
  - [x] add preset grouping to preset config file (each preset's `group` is its parent output dir; `songs-generate-group <name>` generates one group)
  - [x] add a check that a preset group contains each song in the database exactly once, reporting missing/duplicate songs (`check-group [group]`)
- [ ] Code Cleanup and Refactoring
  - [ ] find duplicated code and move into separate functions
  - [ ] find non-pythonic code and refactor it to be more pythonic
- [ ] update README and other documentation
- [ ] find better cover image for 2024-12-30 version of blinding lights
- [ ] find glorp alien Neuro and Evil art for Alien Alien covers
- [x] attempt to automatically get ASCII song titles by finding sets of characters inside parantheses and striping non-alphanumeric characters from that
- [x] update to use the new metadata format from Unofficial Archive that separates english and original language titles and artist names, and splits out the song version identifiers (Neuro Ver., Evil Ver., etc)
- [ ] get list of all output files, and remove all files in out folder not in the list prior to generating
- [ ] add function that can update the database based on the output of the setlist check

## later plans
- [ ] figure out how to package as a graphical program that does everything except download/upload
- [ ] catalog alternate titles and artist names
- [ ] automate updating Duplicates.md and Song List.md
- [ ] switch to rewriting the embedded metadata in the same format as the unofficial archive and tell people to use the metadata customizer instead of making multiple copies with each format
  ~~- [ ] find out if they plan to update the metadata customizer, and if not do it myself~~ they discontinued it
- [ ] add support for metadata customizer presets
- [ ] automatically update duplicates.md
- [x] replace os.system calls with the preferred way to call other programs
- [x] lint the codebase (ruff configured in pyproject.toml)


# Old TODOS
## High-prio
- [x] Add ARG songs, as a separate preset
  - [x] Find dates
- [x] Add roundabout from 1st subathon
- [ ] See if I can use ID3 tags for a FLAC file (to merge most of the code + have access to the album artist tag)
- [x] Check duets for last stream
- [x] Add 3D duplicates

- [x] Add Baka Mitai GX Aura collab https://www.youtube.com/watch?v=K4iLtHy7G2Q
- [ ] Update thumbnail backgound
  - [ ] New thumbnails for duets depending on who's the main singer
  - [ ] Separate v3 cover before/after new neuro mic
  - [ ] New classification for csv/db
  - [ ] Update code in the reading (for generation) and writing (when reading JSON)

## Mid-prio
- [ ] Replace github screenshots with poweramp?
- [x] Preset prefix/suffix (pass preset to Song)
- [x] More complex flag selection with AND/OR
  - [x] Maybe at first just an option in the preset to tell include-type = "AND" | "OR" (same for exclude). Write stack_and function and check for option in preset.
  - [ ] Or have a "complex mode" flag, tell if it's AND->OR or OR->AND. And put conditions in arrays of arrays and apply operation 1 between level1 arrays...
- [x] Find where "fnaf.mp3" is from -> unused
