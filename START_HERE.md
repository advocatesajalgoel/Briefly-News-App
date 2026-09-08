# Start here

This page assumes you have never written a line of code, and never want to.
Follow it in order and you will end up with Briefly on your iPhone's home
screen, updating itself twice a day, for nothing.

It takes about fifteen minutes, most of which is waiting.

---

## What you are about to do

You are going to put this folder onto a free website called GitHub. GitHub will
then, twice a day, on its own computers:

* fetch the news from publishers' own feeds,
* group the reports of the same event together,
* write each one up in thirty words or fewer,
* record the audio briefing,
* and publish the result at a web address of your own.

You open that address on your iPhone once, and add it to your home screen. From
then on it is an icon you tap, like any other app. It works with no signal.

You do not need a Mac. You do not need an Apple developer account. You do not
need to pay anyone. You will not have to touch any of this again.

---

## Step 1 — Get a GitHub account

Go to **[github.com/signup](https://github.com/signup)**.

Use your email address, choose a password, pick a username. It will email you a
code; type it in. That is the whole of it, and it is free.

Write down the username you chose. You will need it in step 5.

---

## Step 2 — Make a place to put the files

Go to **[github.com/new](https://github.com/new)**.

* **Repository name:** `briefly`
* Choose **Public**. (This matters: public repositories get unlimited free
  build time, private ones do not.)
* Leave every other box alone.
* Press the green **Create repository** button.

---

## Step 3 — Upload the files

On the page you land on, find the line that says *"uploading an existing file"*
and click it.

Now drag the **contents** of the `briefly` folder into the box — that is, the
`backend`, `ios`, `site`, `docs`, `tools` and `.github` folders and the loose
files next to them, not the `briefly` folder itself.

> Two things to watch:
>
> * The `.github` folder starts with a dot, which makes it invisible in Finder
>   and in Windows Explorer. On a Mac press **⌘ + Shift + .** to show it; on
>   Windows tick **Hidden items** in the View menu. **Briefly will not build
>   without it** — that folder is the part that does the work.
> * Your browser may take a few minutes to upload it all, and may say nothing
>   while it does. Let it finish.

When the files are listed, scroll to the bottom and press **Commit changes**.

---

## Step 4 — Press the button that builds it

Click **Actions** in the row of tabs along the top of your repository.

If it asks you to enable workflows, press the green button that says you
understand.

In the list on the left, click **Publish site**. Then on the right, press
**Run workflow**, and press the green **Run workflow** button that drops down.

A yellow dot appears. It will take five to ten minutes. You can close the tab
and come back — it runs on GitHub's computers, not yours.

When the dot turns into a green tick, it is done.

---

## Step 5 — Open it on your iPhone

Your address is:

```
https://YOUR-USERNAME.github.io/briefly/
```

with your GitHub username in place of `YOUR-USERNAME`. (The finished build also
prints it: click the green tick, and the summary page shows the address.)

On your iPhone:

1. Open that address **in Safari**. It has to be Safari — Chrome on iPhone
   cannot add things to the home screen.
2. Tap the **Share** button — the square with an arrow coming out of the top.
3. Scroll down the list and tap **Add to Home Screen**.
4. Tap **Add**.

Briefly is now on your home screen. Tap it: full screen, no browser bars, its
own icon. Swipe up for the next story, down for the previous one. Tap the
source line under any story to see every publisher that reported it and read
the originals.

---

## How to use it

* **Swipe up** for the next story, **down** for the one before.
* **The line at the bottom of a card** — "5 sources" — opens the list of every
  publisher that reported the story, what each of their headlines said, and a
  link to each original article.
* **Podcast** plays the day's briefing, narrated from the same facts as the
  cards. Tap a chapter to jump to that story.
* **Saved** keeps stories on your phone. Nothing about what you read is sent
  anywhere.
* **The half-circle at the top right** switches between light and dark.

---

## Things that will happen eventually

**The news stops updating.** GitHub pauses the twice-daily schedule on a
repository nobody has touched for 60 days. Go to Actions → Publish site → Run
workflow, once. That counts as touching it, and the schedule starts again.

**A story looks thin, or a section is empty.** Feeds move and go down. Open the
Actions tab and look at the most recent run — it prints a table of which feeds
answered and which did not, and it switches the dead ones off by itself.

**Everything is fictional.** If the stories mention places like Kalpore or
Ordelia, the live feeds could not be reached and the app fell back to its
built-in sample stories rather than showing you an empty screen. Run the
workflow again later.

---

## What this is not

It is a **web app**, not an App Store app. Two consequences, and they are the
only two:

* You will not find it by searching the App Store, and you cannot send it to a
  friend as an App Store link — though you can send them the web address, and
  they can add it to their own home screen the same way.
* Notifications need to be granted explicitly, and iOS does not let a web app
  refresh in the background — Briefly fetches the latest stories when you open
  it.

Everything else about it is a real app: its own icon, full screen, offline,
your own private copy.

The native iPhone app is in this folder too, in `ios/`. Putting *that* on a
phone needs Apple's signing chain, which means either a Mac or Apple's $99-a-
year developer account. `docs/BUILDING_WITHOUT_A_MAC.md` explains the options
honestly, including which ones are scams.

---

## If something goes wrong

The single most common cause is the missing `.github` folder in step 3 — it is
hidden by default, and without it the Actions tab has nothing to run.

Otherwise: open the Actions tab, click the run that failed, and click the step
with the red cross. Copy what it says and send it back to me. The error text is
the whole diagnosis.
