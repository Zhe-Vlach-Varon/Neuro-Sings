# TODO

## Current Plans

- [ ] take list of songs from a file, and auto detect duplicates based on presence of file in list of new files
- [ ] make it so that the officially released songs will be skipped if not present
- [ ] switch to hashing audio data instead of whole file
  - [x] switch to checking for song presence in DB based on hash of audio data instead of file hash
  - [ ] detect when file metadata doesn't match the database and print a list of issues
  - [x] when generating songs, create a dictionary mapping audio hashes to file names
- [ ] Update cover image generation system
  - [ ] create and use texture atlas or individual images of each possible character used in date strings
    - [x] first pass text atlases
    - [ ] figure out how to straighten up date segments so they line up better
  - [ ] add system to handle split karaoke streams like the 2025 Christmas Karaoke (by split I mean one twin did first half, and the other twin did the second half)
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
- [ ] Add more error checking
  - [ ] Check for and remove empty rows in DB/CSV
  - [ ] Check for and handle fields that are empty string instead of Null
- [ ] Add Debug Mode Print Statements for easier debugging when something goes wrong
- [ ] update Songlist.md
- [ ] find and add credits for new cover arts
- [ ] check and update database
- [ ] Code Cleanup and Refactoring
  - [ ] find duplicated code and move into separate functions
- [ ] update README and other documentation


## later plans
- [ ] figure out how to package as a graphical program that does everything except download/upload



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
- [ ] Preset prefix/suffix (pass preset to Song)
- [x] More complex flag selection with AND/OR
  - [x] Maybe at first just an option in the preset to tell include-type = "AND" | "OR" (same for exclude). Write stack_and function and check for option in preset.
  - [ ] Or have a "complex mode" flag, tell if it's AND->OR or OR->AND. And put conditions in arrays of arrays and apply operation 1 between level1 arrays...
- [x] Find where "fnaf.mp3" is from -> unused
