# Kettlebell Bible 

An Android only (for now) mobile workout logger built with Python using the Flet library.

## About
The **Kettlebell Bible** is a minimalist workout app I designed because originally I kept all the workouts I accumulated over the years in my Notes app on my phone and I lived in constant fear that I would one day lose everything I had gathered.
Moreso, I wanted to give myself an easier way to view the workouts rather than scrolling endlessly through the unfiltered Notes app. All of the features in this application were born from many frustrated days in the gym trying to update workouts, delete old ones, search for the appropriate workout in a clunky Notes app, and switch between the Stopwatch app and the Notes app in between sets. I hopefully have much more to add to this application as time goes on but for now, I have a working app that suits my needs in the gym.

## Features
* **Custom Library:** Create and edit your own workouts in addition to the ones that come preloaded on the app with a locally saved library.
* **Focus Mode:** Integrated stopwatch and rest countdown for tracking rest times in between rounds, plus a round counter for each workout. The countdown starts from the workout's rest time (for example "90 Seconds"), can start itself when you finish a round, and vibrates and flashes when time is up. The screen stays awake while a timer is running. Looks to avoid switching back and forth between other applications.
* **Smart Search:** Filter workouts by equipment and configuration and search through the library using keywords.
* **Offline Storage:** All data is stored locally on the device in a SQLite database that survives app updates.
* **Backup & Restore:** Export the whole library to a JSON file (for example, to Google Drive) and import it again from the menu. Imports merge by workout: new ones are added, newer edits win, and you see a summary before anything changes.

## Build
* **Language:** All work was coded in Python 3.14
* **Framework:** [Flet](https://flet.dev) (Flutter wrapper for Python)
* **Storage:** SQLite, with versioned schema migrations. The bundled `workouts.json` seeds a fresh install once.
* **Version Control:** Git & Github

**Installation:**
* Clone the repo:

```bash
git clone https://github.com/jrfranco04/kettlebell-bible.git
```

* Install dependencies and run the app on your computer:

```bash
pip install -r requirements.txt

flet run main.py
```

On the desktop the database is kept in a local `data/` folder (ignored by git).

**Build an Android APK:**

```bash
flet build apk --exclude workouts.db data Screenshots tests .git __pycache__
```

Add `--bundle-id` and `--product` to install a test copy next to your real app without touching its data.

**Run the tests:**

```bash
python3 -m unittest discover -s tests
```
