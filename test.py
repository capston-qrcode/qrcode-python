import qrcode

code = qrcode.make('https://qrfy.com/?utm_source=Google&utm_medium=CPC&utm_campaign=17680026409&utm_term=qr%20code%20maker&gad_source=1&gclid=Cj0KCQjwkdO0BhDxARIsANkNcrfErfu3V0ztbOAN2_YjxlhdNhLMmjzDfHouAZIx5kZNfoDHi9wHCYoaAmDlEALw_wcB', error_correction=qrcode.constants.ERROR_CORRECT_M)
print(type(code))
code.save("test.png")
