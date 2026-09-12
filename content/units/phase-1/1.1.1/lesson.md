# A program that reads a customer's message

Every one of the three thousand messages Lantern receives each month starts the same way for Tunde: he opens it and finds the order number, so he can look the order up. Sometimes it is right there in the subject line. Sometimes it is buried in the third sentence. Sometimes it is missing, and he has to go hunting by the customer's email address instead. It is a small, dull job, and he does it three thousand times a month.

By the end of this chapter you will have written a program that does that job: it opens one of Lantern's message files, finds the customer's email address and the order number inside it, and prints them. It is about twelve lines long. On the way you will learn what a program actually is, how Python runs one, how it remembers things, how it reads a file, and how it picks pieces out of text. Those four ideas are most of what any program does, so we are going to take them slowly.

You need the course folder you set up in Unit 0.3. Inside it is a copy of Lantern's files: a folder called `messages` with ten customer messages in it, plus `orders.csv`, `deliveries.csv` and `rules.md`. I will call that folder `lantern` and assume your terminal is open inside it. If you type `ls` (or `dir` on Windows) you should see `messages` in the list.

## Running a program

A program is a text file. That is the whole of it. You write instructions into a file, and you ask Python to read the file and carry out the instructions, from the top line to the bottom, one line at a time.

Open your editor, make a new file in the `lantern` folder called `hello.py`, and type these two lines into it exactly:

```python title=hello.py
print("Lantern Home support")
print("Message M-1041")
```

`print` is an instruction that means "show this in the terminal". The thing in the brackets is what to show. The double quotes around `Lantern Home support` tell Python that this is a piece of text to be shown as it is, not an instruction to be carried out. A piece of text in quotes is called a *string*, because it is a string of characters, and you will be using that word constantly from now on.

Save the file. In the terminal, run it:

```text
$ python3 hello.py
Lantern Home support
Message M-1041
```

Here is what happened, and I am going to spell it out because the picture matters more than it seems. You typed `python3 hello.py`, which means "Python, run the instructions in the file `hello.py`". Python opened the file and read the first line. The first line said to print a string, so it printed it. Then Python read the second line and did the same. Then it reached the end of the file and stopped. Two lines in, two lines out, in the order they were written.

That is how every program you will ever write runs: top to bottom, one instruction at a time, each one finishing before the next one starts. When a program does something you did not expect, the first question is always "which line was Python on, and what did it have at that moment?" You will ask that question a thousand times.

## A name that remembers a value

Programs need to hold on to things. Tunde reads the customer's name off the message and then uses it in his reply; the program will need to do the same, which means it needs a way to keep a value around under a name.

Change `hello.py` so it reads:

```python title=hello.py
customer = "Fatima Al-Sayed"
print(customer)
```

The first line is new. Read it as an instruction, not as a statement of fact: it says "take the string `Fatima Al-Sayed` and remember it under the name `customer`". The `=` sign is doing that remembering. It is not saying two things are equal, the way it does in arithmetic. It is an action: work out whatever is on the right, then store it under the name on the left. Python calls a name like `customer` a *variable*, and from here on so will I.

Before you run it, decide what you expect the second line to print. Then check.

<details><summary>What does it print?</summary>

```text
$ python3 hello.py
Fatima Al-Sayed
```

`print(customer)` prints the value stored under the name `customer`, which is the string. There are no quotes around `customer` in that line, and that is the whole difference: `customer` without quotes means "the thing this name refers to". `"customer"` with quotes would mean the six letters c-u-s-t-o-m-e-r, and printing that would print the word `customer`, which is not what we want.

</details>

Try it the other way, so the difference sticks. Change the second line to `print("customer")`, run it, and watch it print the word instead of the name. Then change it back.

A variable can be given a new value. Add two lines:

```python title=hello.py
customer = "Fatima Al-Sayed"
print(customer)
customer = "Joseph Mwangi"
print(customer)
```

```text
$ python3 hello.py
Fatima Al-Sayed
Joseph Mwangi
```

The third line stores a new string under the same name, and the old one is gone. Notice what that means about order: the first `print` happened before the reassignment, so it printed the first name. If you moved the third line above the first `print`, both would print Joseph. The variable holds whatever was most recently stored in it, at the moment the line runs. Top to bottom, one line at a time.

## Reading the message file

Now the real thing. The customer's message is in a file, `messages/M-1041.txt`, and the program needs to get the text out of that file and into a variable. Make a new file called `read_message.py`:

```python title=read_message.py
with open("messages/M-1041.txt") as file:
    text = file.read()

print(text)
```

There are three new things here. Take them one at a time.

`open("messages/M-1041.txt")` asks the operating system to open that file for reading. The string is the path to the file, relative to the folder your terminal is in: go into `messages`, find `M-1041.txt`. The forward slash works on every operating system, including Windows.

`with ... as file:` gives the opened file the name `file` for as long as the lines indented underneath it are running, and closes the file when they finish. The colon at the end of the line and the four spaces at the start of the next line are how Python knows which lines belong inside the `with`. Python is strict about this: the indented lines are inside, the first line back at the left margin is outside. That is why `print(text)` is not indented. It runs after the file has been closed, and it does not need the file, only the text.

`file.read()` pulls the whole content of the file out as one string, and `=` stores that string under the name `text`. The dot between `file` and `read` means "do `read` to `file`". You will see that dot everywhere: it is how you ask a thing to do one of the things it knows how to do.

Run it.

```text
$ python3 read_message.py
From: fatima.alsayed@example.com
Received: 2026-09-03 09:14
Subject: Broken kettle lid

Hello,
I received my kettle yesterday, order 48213. The lid is cracked right across, I have attached a photo. I would like a replacement please or my money back, either is fine.
Thank you
Fatima
```

That is Fatima's message, exactly as it sits in the file, printed by a program you wrote. It is a small moment but it is a real one: your program just read something that was not typed into it.

## When the file is not where you said

Before going on, I want you to see what happens when this goes wrong, because it will, often, and the error message is more helpful than it first appears.

Change the first line so the path says `message` instead of `messages`, without the s:

```python title=read_message.py line=1
with open("message/M-1041.txt") as file:
```

Run it again.

```text
$ python3 read_message.py
Traceback (most recent call last):
  File "/home/you/lantern/read_message.py", line 1, in <module>
    with open("message/M-1041.txt") as file:
         ^^^^^^^^^^^^^^^^^^^^^^^^^^
FileNotFoundError: [Errno 2] No such file or directory: 'message/M-1041.txt'
```

Your path will be different from `/home/you/lantern`, but the rest will match. Read it from the bottom up, because the bottom line is the one that says what went wrong: `FileNotFoundError`, no such file or directory, and then the exact path it looked for. Above that, Python tells you which line it was on (line 1) and shows you the line, with a row of carets under the part it was trying to carry out when it failed. Everything you need is in those five lines: what, where, and which piece.

Nothing printed after the error, because Python stopped at line 1. It never reached `print(text)`. A program halts at the first instruction it cannot carry out; it does not skip the bad line and carry on. Put the s back:

```python title=read_message.py line=1
with open("messages/M-1041.txt") as file:
```

This kind of message is called a *traceback*, and you will read hundreds of them. None of them is a judgment. Each one is Python telling you, as precisely as it can, where it got stuck.

## Text is a row of characters

Now we have the message in `text`. We want two things out of it: the email address on the first line, and the order number, which in this message is in the sentence "I received my kettle yesterday, order 48213."

To pick pieces out of a string you need to know how Python sees one. It sees a row of characters, each with a position, starting from zero. For this part I want you to use the interactive prompt rather than a file, because it lets you try one thing at a time and see the answer at once. In the terminal, type `python3` on its own and press Enter. You will see a `>>>` prompt. Anything you type there runs immediately, and if it produces a value, Python shows you the value.

Load the message first, the same way as in the file (the prompt shows `...` while it waits for the indented line; press Enter on an empty line to finish the block):

```python
>>> with open("messages/M-1041.txt") as file:
...     text = file.read()
...
>>> len(text)
283
```

`len` gives the length of a string: this message is 283 characters, counting spaces and the invisible line breaks. Now ask for single characters by position, in square brackets:

```python
>>> text[0]
'F'
>>> text[1]
'r'
>>> text[5]
' '
```

Position 0 is the first character, so `text[0]` is the `F` of `From`. Position 5 is the space after the colon. Starting from zero rather than one feels wrong for about a week and then becomes normal; almost every programming language does it.

You can ask for a run of characters with two positions separated by a colon. Before you type this, guess what it gives:

```python no-run
>>> text[0:5]
```

<details><summary>What comes back?</summary>

```python
>>> text[0:5]
'From:'
```

Positions 0, 1, 2, 3 and 4. The second number is where to stop, and the character at that position is not included. So `text[0:5]` is five characters, from position 0 up to but not including position 5. This is the second thing that feels wrong for a week. The reason for it is that the length of the piece is the difference between the two numbers, 5 minus 0 is 5, which turns out to be very convenient once you are computing those positions rather than typing them.

</details>

This is called a *slice*, and it is how we will cut the order number out. But to slice it out we need to know where it is, and that changes from message to message. So the last piece is a way to search.

```python
>>> text.find("order")
127
```

`find` searches the string for the piece you give it and tells you the position where it starts. The word `order` begins at position 127 of this message. Check it by slicing:

```python
>>> text[127:138]
'order 48213'
```

Eleven characters starting at 127: `order`, a space, and the five digits. The order number itself starts six characters after the word begins (five letters and a space) and is five digits long. So:

```python
>>> text[127 + 6:127 + 11]
'48213'
```

Python works out the arithmetic inside the brackets first, 133 and 138, and then slices. That is the order number, cut out of the message by position.

If `find` cannot find the piece, it gives back `-1`, which is not a position at all. Keep that in mind; it is going to matter at the end of the chapter.

Leave the prompt by typing `exit()` and pressing Enter.

## Cutting out the order number in the program

We know how to do it by hand now. In the program, the position is not going to be typed in as 127, because the next message will have it somewhere else. The program has to ask. Add to `read_message.py`:

```python title=read_message.py
with open("messages/M-1041.txt") as file:
    text = file.read()

position = text.find("order")
order_number = text[position + 6:position + 11]
print(order_number)
```

The fourth line asks where the word `order` starts and stores the answer, 127 for this message, under the name `position`. The fifth line slices from six characters after that to eleven characters after that, exactly as we did at the prompt, and stores the five characters under `order_number`. I have named the variables for what they hold, and I would ask you to do the same in your own programs: in a month, `p` and `o` will mean nothing to you, and `position` and `order_number` still will.

```text
$ python3 read_message.py
48213
```

Notice that `print(text)` is gone. We do not want the whole message any more, only the number.

## Cutting out the email address

The email address is on the first line, after `From: `. We could find it with `find` and slices the way we found the order number, but there is a more natural tool for "the first line", and it introduces something you will use every day.

```python
>>> lines = text.splitlines()
>>> lines[0]
'From: fatima.alsayed@example.com'
```

`splitlines` cuts the string at every line break and gives back the pieces as a *list*: an ordered collection of values, which you can ask for by position in the same square brackets. `lines[0]` is the first line. Try `lines[1]` and `lines[2]` and you will get the `Received` and `Subject` lines.

The first line still has `From: ` at the front. Strings know how to swap one piece for another:

```python
>>> lines[0].replace("From: ", "")
'fatima.alsayed@example.com'
```

`replace` gives back a copy of the string with every occurrence of the first piece replaced by the second. Replacing `From: ` with nothing at all, the empty string `""`, deletes it. The original string is not changed; `replace` hands you a new one, which is why we have to store the result if we want to keep it.

Into the program:

```python title=read_message.py
with open("messages/M-1041.txt") as file:
    text = file.read()

position = text.find("order")
order_number = text[position + 6:position + 11]

lines = text.splitlines()
email = lines[0].replace("From: ", "")

print("From:", email)
print("Order:", order_number)
```

The last two lines show something new about `print`: you can give it several things, separated by commas, and it prints them on one line with a space between each. Predict the output before you run it.

<details><summary>Output</summary>

```text
$ python3 read_message.py
From: fatima.alsayed@example.com
Order: 48213
```

If you expected `From:fatima.alsayed@example.com` with no space, that is the comma doing its work: `print` puts one space between each of the things you give it.

</details>

## The whole program

Here is `read_message.py` as it stands, so you can compare yours against it line by line. Every line in it is one you have already seen and run.

```python title=read_message.py
with open("messages/M-1041.txt") as file:
    text = file.read()

position = text.find("order")
order_number = text[position + 6:position + 11]

lines = text.splitlines()
email = lines[0].replace("From: ", "")

print("From:", email)
print("Order:", order_number)
```

Read it top to bottom the way Python does. Open the file and read its text. Find where `order` is and slice out the five digits after it. Split the text into lines, take the first one, remove the label. Print both. Nine instructions, and it does the first thing Tunde does with every message.

Try it on another message. Change the path on the first line to Ana Souza's message, the one about returning a desk lamp:

```python title=read_message.py line=1
with open("messages/M-1043.txt") as file:
```

```text
$ python3 read_message.py
From: ana.souza@example.com
Order: 48231
```

Then try `messages/M-1045.txt`, Lan's dented pots, where the order number sits inside brackets in the middle of a sentence:

```python title=read_message.py line=1
with open("messages/M-1045.txt") as file:
```

```text
$ python3 read_message.py
From: lan.nguyen@example.com
Order: 48237
```

The program does not care where in the message the word `order` is, because it asks.

## Where this breaks

Now point it at Joseph Mwangi's message about blue bedsheets:

```python title=read_message.py line=1
with open("messages/M-1042.txt") as file:
```

Before you run it, open `messages/M-1042.txt` in your editor, read what Joseph wrote, and guess what the program will print for the order number.

<details><summary>What it prints</summary>

```text
$ python3 read_message.py
From: jmwangi@example.com
Order: d GRE
```

Joseph wrote "i ordered GREY bedsheets". The word `ordered` contains the word `order`, so `find` stopped there, at the first match, and our slice cut five characters out of the middle of `ordered GREY`. The real order number, 48220, is in the next sentence, after the phrase "order number is". Our program has no way to know that the first `order` was the wrong one.

</details>

Ivan Petrov's message, `M-1044.txt`, is worse. Point the program at it:

```python title=read_message.py line=1
with open("messages/M-1044.txt") as file:
```

```text
$ python3 read_message.py
From: ivan.petrov@example.com
Order:  ivan
```

Ivan wrote `Order 48244` with a capital O, and `find` is looking for a lower-case `order`. It finds nothing and gives back `-1`. Then `position + 6` is `5` and `position + 11` is `10`, and `text[5:10]` is the five characters starting at position 5 of the message: the space after `From:` and the first four letters of Ivan's email address. The program prints that as the order number. No error, no traceback. Just a wrong answer, delivered with confidence.

That last kind of failure is the one you should be most afraid of, and it is the reason this course spends so long on checking things. A program that crashes tells you. A program that prints ` ivan` where an order number should be tells you nothing, and if that value went into the decisions spreadsheet, Wei would find it a year later and want to know how.

Fixing this properly needs two things the program cannot yet do: look at each word in the message in turn and ask whether it looks like an order number, and decide what to do when the answer is no. That is the next chapter. For now, the program works for messages that say "order" followed by the number, which is most of them, and the assignment below asks you to finish a version of it yourself, without the piece that finds the number, so that the slice is yours.
