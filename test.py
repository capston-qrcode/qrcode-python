import qrcode

code = qrcode.make("뷁")
print(type(code))
code.save("test.png")