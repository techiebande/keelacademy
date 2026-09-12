# Finish read_message.py

The chapter built `read_message.py` in front of you. The assignment gives you the same program with one piece taken out, the piece that finds the order number, and asks you to write it.

In `starter/` you will find `read_message.py`. It already opens Fatima's message, splits it into lines, pulls the email address off the first line, and prints both values at the end. Between those parts is a gap, marked by a comment and a line that sets `order_number` to an empty string. Replace that line with the two lines that do the real work: ask the text where the word `order` starts, and slice out the five characters that begin six characters after that.

Do not type `48213` into the program. The point is that the program finds it. When you have it working on `M-1041.txt`, change the path to `M-1043.txt` and `M-1045.txt` and make sure the number changes with it. Then change it back to `M-1041.txt`, because that is the message the checks use, and submit.

## How it is checked

Four checks run against your file, and the result names each one.

`prints-email` runs your program and looks for the line `From: fatima.alsayed@example.com`. The starter already does this, so if it fails, something in the part you did not change has been disturbed. Compare against the chapter's final listing.

`prints-order-number` runs your program and looks for `Order: 48213`. This is the one your two lines have to earn.

`order-number-is-found-not-typed` reads your program's text and fails if the digits `48213` appear anywhere in it. A program that prints the right answer because the answer was typed in has not read the message.

`uses-find-and-a-slice` reads your program's text and fails if it does not use `.find(` and square brackets. There are other ways to get the number out, and you will learn several, but this assignment is about the one the chapter taught.

The checks run in a few seconds. A check that says "not yet" is pointing at one line of your program, and the section below covers the usual reasons.

## If you get stuck

### Order prints as an empty line

Your program still has `order_number = ""` in it, or your two new lines came after the `print`. Python runs top to bottom, so `order_number` has to be given its real value before the line that prints it.

### Order prints five characters that are not the number

Count again from the start of the word `order`. `o r d e r` is five letters, then a space, so the first digit is at `position + 6`. The number is five digits long, so the slice ends at `position + 11`. If you wrote `position + 5`, you will get the space and four digits.

### NameError: name 'position' is not defined

You used a name on one line that you did not create on an earlier line. Check the spelling matches exactly between the line with `text.find` and the line with the slice; `position` and `Position` are different names to Python.

### The checks pass on my machine but the email check fails

The checks run your program against `messages/M-1041.txt`. If you left the path pointing at a different message when you submitted, the email will be someone else's. Change the path back to `M-1041.txt` and resubmit.
