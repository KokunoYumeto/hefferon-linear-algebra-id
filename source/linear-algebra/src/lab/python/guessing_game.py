# guessing_game.py
"""guessing_game.py

Tebak bilangan antara 1 dan 10.
"""
import random
CHOICE = random.randint(1,10)

def test_guess(guess):
    """Tentukan apakah tebakan benar, lalu cetak sebuah pesan.
    """
    if (guess < CHOICE):
        print("  Maaf, tebakan Anda terlalu kecil")
        return False
    elif (guess > CHOICE):
        print("  Maaf, tebakan Anda terlalu besar")
        return False
    print("  Tebakan Anda benar!")
    return True

flag = False
while (not flag):
    guess = int(input("Tebak sebuah bilangan bulat antara 1 dan 10: "))
    flag = test_guess(guess)
