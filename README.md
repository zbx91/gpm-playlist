
# The Google Play Music Automated Daily Playlist Manager

This is intended to be a 100% cloud-based solution for generating automated daily playlists for Google Play Music. Currently, it is designed for my own purposes, but I might eventually open up the gpm-playlist GAE app for others to be able to use it as well.

The original basis for this app was my use of the Smart Playlist functionality in Apple's iTunes, which I needed in order to load music from my own personal music library on my G1 iPhone. I wanted a way to work my way through my music library, leaving no songs out of the cycle, but in a somewhat intelligent manner, while also providing random selections of music. To this end, I developed lists that were based on specific:

* **Least Recently Added [LRA]** *(and not played)* -- This was a simple list structure that found all of the unplayed music, and found the tracks that were the oldest in my library from them, and added a selection from these. The concept is that all "new" (unplayed) music would eventually be played. When I run out of unplayed tracks, these become simply random.
* **Least Recently Played [LRP]** -- The counter to the above list, this list specifically focuses on tracks that have been played, and finds the ones that have not been played for the longest amount of time, and adds a selection from these. This keeps my music rotating and ensures I keep listening to everything in my library. If I don't have enough played tracks, the remaining ones are random.
* **Least Often Played [LOP]** -- This simply gets a selection of the tracks that have the lowest play count. This helps keep balance on the frequency I play my music, so that songs that have not been played often end up in my list to get played more.
* **Random [RAND]** -- An equal number of tracks as picked from all of the above lists, is picked at random from what is left.

As my music library got larger over the years, I began to divide my music up into different categories, essentially partitioning my music -- each track is assigned to one, and only one category. I made this distinct from Genre, but in a sense it is similar to Genre, except that Genre is something that a track typically is already given, while I wanted to pick and choose tracks individually to put them into my individual category/partition "buckets". Some albums might have tracks that fall into multiple categories, even if they all have the same Genre.  I then applied all of the above defined groups to each category separately, combining the results together into a single playlist, this ensures that all of my categories are represented in my playlist each day.

Another step I took was to look at the ratings I had set on my music. iTunes allowed for 5-start ratings, but I found I really had only two types of ratings I was interested in: Favorites and Normal tracks. For Google Play Music, this would be Thumbs-up vs no thumbs. Thumbs-down would be tracks that are excluded from the playlist processing entirely (and potentially could be removed from my library, if I desired).

For the rating processing, I run all of the above groups for a category, just on the Favorite tracks (thumbs-up) first, then I run it a second time with thumbs-up or not rated grouped together. This makes favorites appear more frequently than non-favorites. I found that if I made the Favorites group be 1/2 the size of the combined group, this helped balance things out more to my liking.

All of the above rules result in a good mix of music for my playlist each day. I built this design using smart playlists, and was able to synchronize my G1 iPhone with iTunes each morning to load my next batch of music for the day. This worked until two things happened: my iTunes application, running in a VM running Windows inside my Linux system crashed horribly, and recovering became difficult (at best). Plus, my contract on my G1 iPhone ended, and I just was not inclined to continue with Apple. So, I began looking at other options. I settled quickly on the Firefly music server, to serve a music stream to my computer wherever I was. I was able to recreate my smart playlists fairly well, and was able to use my existing music library to continue the work, but now it was a stream of music rather than music on my phone.

Firefly Server had its issues, and I migrated to Squeezebox Server. I rewrote my playlists into SQL queries, and was able to continue the processing of my playlist from my own home-based server. Squeezebox Server started to be somewhat limiting for me (and I didn't like writing everything as SQL queries), so I rebuilt my server using Music Player Daemon (MPD). MPD have me freedom to write my playlist in a language I preferred -- Python. I ended up building the entire system simply, no longer limited by a particular framework (since MPD is fairly simple in how it does things), and then my personal server failed. I had not been able to continue my music streaming from home after that.

At the same time, Google started their music service... with the ability to upload a TON of music to be able to be streamed back over the internet, even to my Android phone... but it is limited in that there is no equivalent to the smart playlist processing I had desired. But, Google also has a cloud-based programming platform, their App Engine, which runs Python. So... this project is my attempt to make Google App Engine drive a system that handles the processing of a daily playlist that will be available in Google Play Music. Thanks to the gmusicapi library by @simon-weber, that gives Python an unofficial API to access the Google Play Music system, I believe this is truly possible.

The stated goals for this project:

1. Generate a Daily Playlist, as explained by the above rules, and place it in Google Play Music's playlists. This playlist is reloaded every day with new songs based on these rules -- through a simple cron job.
2. Allow for managing songs to place them into individual category/partitions (through a web-based app).
3. Allow for configuring specialized time-based categories for "holiday" time periods that promotes songs flagged for a particular holiday (like Christmas, Halloween, etc), mixing in songs from these holidays during the defined time periods.
4. Plus more...
