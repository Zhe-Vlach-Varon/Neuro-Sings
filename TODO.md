# TODO

## High-Priority
- [ ] update DB to point to the files in the Unofficial Archive V3
- [ ] finish updating code to draw files from Unofficial Archive V3
## Medium-Priority
- [ ] take list of songs from a file, and auto detect duplicates based on presence of file in list of new files
- [ ] switch to checking for song presence in DB based on audio fingerprint instead of file hash, or just remove the hash checks if audio fingerprint checking isn't feasable
- [ ] Update cover image generation system
  - [ ] create and use texture atlas or individual iamges of each possible character used in date strings
    - [ ] is First Coffee a monospace font, if not figure out spacing
  - [ ] add system to handle split karaoke streams like the 2025 Christmas Karaoke (by split I mean one twin did first half, and the other twin did the second half)
  - [ ] add configurable base image sources
    - [ ] add more background images
      - [ ] Neuro Background Images
        - [ ] Neuro v1
        - [ ] Neuro v2
        - [ ] Neuro v3 Long Hair Old Mic
        - [ ] Neuro v3 Long Hair New Mic
        - [ ] Neuro v3 Hair Loops Old Mic ??
          - [ ] check when Neuro got her new hairstyle and when she got her new Mc
        - [ ] Neuro v3 Long Hair New Mic
        - [ ] Neuro v3 Hair Loops New Mic
      - [ ] Evil Background Images
        - [ ] Evil v3 Guitar
          - [ ] was their a Evil v2 Guitar?
        - [ ] Evil early Neuro Recolors
        - [ ] Evil v2
        - [ ] Evil v3
      - [ ] Duet Backgrounds
        - [ ] Neuro on right
        - [ ] Evil on right
        - [ ] Both twins v2 Models
        - [ ] Neuro v3 Evil v2
        - [ ] Both twins v3 Models
          - [ ] Evil New Mic Neuro Old Mic
          - [ ] Both twins New Mics
        - [ ] Sometimes only one twin would have a Mic
- [ ] Add more error checking
  - [ ] Check for and remove empty rows in DB/CSV
  - [ ] Check for and handle entries that are empty string instead of Null
- [ ] Add Debug Mode Print Statements for easier debugging when something goes wrong
- [ ] Add way to specify that a song is a duplicate of one that is already in the DB
- [ ] update Songlist.md
- [ ] find and add credits for new cover arts













# Old TODOS
## High-prio
- [x] Add ARG songs, as a separate preset
  - [x] Find dates
- [x] Add roundabout from 1st subathon
- [ ] See if I can use ID3 tags for a FLAC file (to merge most of the code + have access to the album artist tag)
- [x] Check duets for last stream
- [ ] Add 3D duplicates

- [ ] Add Baka Mitai GX Aura collab https://www.youtube.com/watch?v=K4iLtHy7G2Q
- [ ] Update thumbnail backgound
  - [ ] New thumbnails for duets depending on who's the main singer
  - [ ] Separate v3 cover before/after new neuro mic
  - [ ] New classification for csv/db
  - [ ] Update code in the reading (for generation) and writing (when reading JSON)

## Mid-prio
- [ ] Replace github screenshots with poweramp?
- [ ] Preset prefix/suffix (pass preset to Song)
- [ ] More complex flag selection with AND/OR
  - [ ] Maybe at first just an option in the preset to tell include-type = "AND" | "OR" (same for exclude). Write stack_and function and check for option in preset.
  - [ ] Or have a "complex mode" flag, tell if it's AND->OR or OR->AND. And put conditions in arrays of arrays and apply operation 1 between level1 arrays...
- [x] Find where "fnaf.mp3" is from -> unused
