from werkzeug.security import generate_password_hash

password = input("Ingresa la contraseña: ")
hashed = generate_password_hash(password)
hashed2 = generate_password_hash(password, method="pbkdf2:sha256")
hashed3 = generate_password_hash(password, method="pbkdf2:sha256:150000")
print("\nHash generado:")
print(hashed)
print("------------------------------------------------------------------------------")
print(hashed2)
print("-------------------------------------------------------------------------------")
print(hashed3)