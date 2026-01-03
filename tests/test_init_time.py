import sys, time
sys.path.insert(0, 'd:/Dev/KG_Chat_PyQt6/src')
from PyQt6.QtWidgets import QApplication
from core.accounts import AccountManager
from ui.ui_chat import ChatWindow

app = QApplication([])
acc = AccountManager().get_active_account()
print('Active account:', acc['login'])
start = time.perf_counter()
w = ChatWindow(account=acc)
init_time = time.perf_counter() - start
print(f'ChatWindow init took {init_time:.3f} sec')
# Run a short event loop to let worker start
for _ in range(10):
    app.processEvents()
    time.sleep(0.1)
print('User widgets count (layout count):', w.user_list_widget.users_layout.count())
w.close()
app.quit()
