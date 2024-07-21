import qrcode

code = qrcode.make("01234567890123450123456789012345", error_correction=qrcode.constants.ERROR_CORRECT_H)
print(type(code))
code.save("test.png")
