# Kettlebell Bible 

An Android only (for now) mobile workout logger built with Python using the Flet library.

## About
The **Kettlebell Bible** is a minimalist workout app I designed because originally I kept all the workouts I accumulated over the years in my Notes app on my phone and I lived in constant fear that I would one day lose everything I had gathered.
Moreso, I wanted to give myself an easier way to view the workouts rather than scrolling endlessly through the unfiltered Notes app. All of the features in this application were born from many frustrated days in the gym trying to update workouts, delete old ones, search for the appropriate workout in a clunky Notes app, and switch between the Stopwatch app and the Notes app in between sets. I hopefully have much more to add to this application as time goes on but for now, I have a working app that suits my needs in the gym.

##Features
* **Custom Library:** Create and edit your own workouts in addition to the ones that come preloaded on the app with a locally saved library.
* **Focus Mode:** Integrated stopwatch for easy tracking of rest times in between rounds. Looks to avoid switching back and forth between other applications.
* **Smart Search:** Filter workouts by equipment and configuration and search through the library using keywords.
* **Offline Storage:** Mentioned above, but all data is stored locally on the device (JSON persistence).

## Build
* **Language:** All work was coded in Python 3.14
* **Framework:** [Flet](https://flet.dev) (Flutter wrapper for Python)
* **Storage:** JSON Flat-file database
* **Version Control:** Git & Github

**Installation:**
* Clone the repo:

```
bash

git clone 

[https://github.com/jrfranco04/kettlebell-bible.git](https://github.com/jrfranco04/kettlebell-bible.git)
```

* Install dependencies:

```
bash 

pip install flet

* Run the app

flet run main.py
```


