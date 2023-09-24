'''
Communication and live plotting over USB serial with solutions for
parallelism and other basic concerns.
'''
import time
import tkinter as tk
from tkinter import ttk, filedialog#, simpledialog
import threading
import serial
import pandas as pd
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import matplotlib.pyplot as plt
plt.style.use('bmh')

class SimpleDAQ:
    '''
    Tkinter-based data acquisition and embedded system communication.
    '''
    def __init__(self, mc_data_dict, update_delay_seconds=1):
        #region Initialization
        self.log = []
        self.pressure_data = []
        self.time_data = []
        self.start_time = time.time()
        self.mc_data_dict = mc_data_dict
        self.update_delay_seconds = update_delay_seconds
        self.datafilepath, self.logfilepath, self.rawserialpath = None, None, None
        self.serial_data_packet = ""
        self.lock = threading.Lock()
        self.exit_signal = threading.Event()
        self.last_save_time = 0
        self.serial_connected = False
        #endregion

        #region Initialize Tkinter GUI, prompt user for COM port
        self.root = tk.Tk()
        self.root.withdraw()  # Hide the Tkinter root window
        d = COM_Port_Dialogue(self.root)
        self.port, self.baud_rate = d.result
        self.root.destroy()  # Close the Tkinter root window
        #endregion

        self.ser = serial.Serial(self.port, self.baud_rate)
        self._define_save_files()
        self._start_gui()

    def _start_gui(self):
        #region Initialize Tkinter root window, paned window, control frame, buttons
        self.root = tk.Tk()
        self.root.title("Data Logging GUI")

        paned_window = tk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        paned_window.pack(fill=tk.BOTH, expand=1)
        control_frame = tk.Frame(paned_window, width=200, height=400, bg='lightgrey')
        control_frame.pack_propagate(False)
        #endregion

        #region Control buttons
        ttk.Button(control_frame, text="Exit", command=self._exit_program).pack(side=tk.TOP, pady=10)
        self.status_label = tk.Label(control_frame, text="Status: Connected", bg='lightgrey')
        self.status_label.pack(side=tk.TOP, pady=10)

        paned_window.add(control_frame)
        #endregion

        #region Matplotlib Figure
        self.fig = Figure(figsize=(6, 4), dpi=175)
        self.ax = self.fig.add_subplot(111)
        self.canvas = FigureCanvasTkAgg(self.fig, master=paned_window)
        self.canvas.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=1)

        paned_window.add(self.canvas.get_tk_widget())
        #endregion

        #region Start Main Loop
        if self.datafilepath:
            self.serial_thread = threading.Thread(target=self._read_serial)
            self.serial_thread.start()
            self.root.after(int(self.update_delay_seconds*1000), self._update)
            self.root.mainloop()
        #endregion

    def _define_save_files(self):
        self.datafilepath = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV files", "*.csv")])
        self.logfilepath = self.datafilepath.replace('.csv', '_log.txt')
        self.rawserialpath = self.datafilepath.replace('.csv', '_raw_serial.txt')
        if self.datafilepath:
            self.log.append(f"Program started at {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())}")
            with open(self.logfilepath, 'w', encoding='utf8') as f:
                for entry in self.log:
                    f.write(f"{entry}\n")
            self.log.append(f"Data will be saved to {self.datafilepath}")

    def _read_serial(self):
        while not self.exit_signal.is_set(): # Exit signal shuts thread down gracefully
            # Try to read from serial port
            try:
                ser_data = self.ser.readline().decode('utf-8').strip()
                if ser_data:  # Check if the data is not empty
                    with self.lock:
                        self.serial_data_packet = ser_data
                        self.serial_connected = True
                    with open(self.rawserialpath, "a", encoding='utf8') as f:
                        f.write(f"{ser_data}\n")
            # Fail to read from serial port
            except (serial.SerialException, AttributeError):
                with self.lock:
                    self.serial_connected = False
                # Attempt to reconnect to serial port
                while not self.serial_connected:
                    try:
                        self.ser.close()
                        self.ser = serial.Serial(self.port, self.baud_rate)
                        with self.lock:
                            self.serial_connected = True
                    except (serial.SerialException, AttributeError):
                        pass

    def _save_files(self):
        #Save runtime data to external text files
        time_seconds = time.time()
        current_time = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(time_seconds))
        self.log.append(f'Saved data at {current_time}')
        df = pd.DataFrame({"Time": self.time_data, "Pressure": self.pressure_data})
        df.to_csv(self.datafilepath, index=False)
        with open(self.logfilepath, 'w', encoding='utf8') as f:
            for entry in self.log:
                f.write(f"{entry}\n")
        self.last_save_time = time_seconds

    def _update(self):
        try:
            with self.lock:
                ser_data = self.serial_data_packet

            run_duration = time.time() - self.start_time
            self.pressure_data.append(float(ser_data))
            self.time_data.append(run_duration)

            #region DAQ plotting
            self.ax.clear()
            self.ax.set_title('Data Acquisition')
            self.ax.set_xlabel('Time (s)')
            self.ax.set_ylabel('Sensor Data')
            self.ax.minorticks_on()
            self.ax.plot(self.time_data, self.pressure_data)
            self.ax.grid(True, which='major', color='silver', linewidth=0.375, linestyle='-')
            self.ax.grid(True, which='minor', color='lightgrey', linewidth=0.2, linestyle='--')
            self.canvas.draw()
            #endregion

            #region save runtime data, update status
            current_time = time.time()
            if current_time - self.last_save_time >= 10:
                self._save_files()
            
            with self.lock:
                if self.serial_connected:
                    self.status_label.config(text=f"USB Port: {self.ser.port}\nStatus: Connected", fg='green', font=("Helvetica", 12, "bold"))
                else:
                    self.status_label.config(text="USB Port: Unknown\nStatus: Disconnected", fg='red', font=("Helvetica", 12, "bold"))
                    self.log.append(f"Serial port disconnected at {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())}")
            #endregion

        except Exception as err:
            # Update status label for disconnected state
            self.status_label.config(text="Unhandled Exception", fg='red', font=("Helvetica", 12, "bold"))
            self.log.append(f"Unhandled error: {err}")

        finally:
            self.root.after(int(1000*self.update_delay_seconds), self._update)

    def _exit_program(self):
        self.exit_signal.set()
        self.serial_thread.join()
        self.log.append(f"Program exited at {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(time.time()))}")
        with open(self.logfilepath, 'w', encoding='utf8') as f:
            for entry in self.log:
                f.write(f"{entry}\n")
        self.ser.close()
        self.root.quit()
        self.root.destroy()


#region custom Tkinter objects
class COM_Port_Dialogue(tk.simpledialog.Dialog):
    # User prompt for com port (string) and baud rate (int)
    def body(self, master):
        tk.Label(master, text="COM port:").grid(row=0)
        tk.Label(master, text="Baud rate:").grid(row=1)
        self.e1 = tk.Entry(master)
        self.e2 = tk.Entry(master)
        self.e1.insert(0, "COM6")  # default value
        self.e2.insert(0, "115200")  # default value
        self.e1.grid(row=0, column=1)
        self.e2.grid(row=1, column=1)
        return self.e1

    def apply(self):
        self.result = (self.e1.get(), int(self.e2.get()))
#endregion

if __name__ == '__main__':
    sdaq = SimpleDAQ({}, 1/4)
