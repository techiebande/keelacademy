# read_message.py
# Reads one of Lantern's customer messages and prints the customer's email
# address and the order number found in the message.

with open("messages/M-1041.txt") as file:
    text = file.read()

lines = text.splitlines()
email = lines[0].replace("From: ", "")

# Find where the word "order" starts, then slice out the five digits that
# follow it (five letters and a space after the start of the word), and store
# them under the name order_number.

order_number = ""

print("From:", email)
print("Order:", order_number)
