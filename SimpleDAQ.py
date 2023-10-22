'''
Communication and live plotting over USB serial with solutions for
parallelism and other basic concerns.
'''
import time
import tkinter as tk
from tkinter import ttk, filedialog, simpledialog
import threading
import ast
import json
import serial
import pandas as pd
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import matplotlib.pyplot as plt
plt.style.use('bmh')

class SimpleDAQ:
    '''Class implementing serial communication, Tkinter GUI, data processing, and data storage.'''
    def __init__(self, mc_data_dict, setpoint_dict=None, update_delay_seconds=1, graph_title='', graph_ylabel='Sensor Data', setpoint_check_precision=.001):
        self.log = []
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
        self.data_channels = [[] for k in mc_data_dict.keys()]
        self.graph_title = graph_title
        self.graph_ylabel = graph_ylabel
        self.setpoints = setpoint_dict
        self.setpoint_check_precision = setpoint_check_precision

        self.root = tk.Tk()
        self.root.withdraw()
        d = COM_Port_Dialogue(self.root)
        self.port, self.baud_rate = d.result
        self.root.destroy()

        self.ser = serial.Serial(self.port, self.baud_rate)
        self._define_save_files()
        self._start_gui()

    def _start_gui(self):
        self.root = tk.Tk()
        self.root.title("Data Logging GUI")

        paned_window = tk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        paned_window.pack(fill=tk.BOTH, expand=1)
        control_frame = tk.Frame(paned_window, width=200, height=400, bg='lightgrey')
        control_frame.pack_propagate(False)

        ttk.Button(control_frame, text="Exit", command=self._exit_program).pack(side=tk.TOP, pady=10)
        self.status_label = tk.Label(control_frame, text="Status: Connected", bg='lightgrey')
        self.status_label.pack(side=tk.TOP, pady=10)

        paned_window.add(control_frame)

        setpoint_frame = tk.Frame(control_frame)
        setpoint_frame.pack(side=tk.TOP, padx=10, pady=10)
        tk.Label(setpoint_frame, text="Setpoints").pack()

        if self.setpoints:
            self.setpoint_entries = {}
            for name, value in self.setpoints.items():
                frame = tk.Frame(setpoint_frame)
                frame.pack(side=tk.TOP, padx=5, pady=5)
                tk.Label(frame, text=name).pack(side=tk.LEFT)
                entry = tk.Entry(frame)
                entry.insert(0, str(value))
                entry.pack(side=tk.RIGHT)
                self.setpoint_entries[name] = entry

        self.fig = Figure(figsize=(6, 4), dpi=175)
        self.ax = self.fig.add_subplot(111)
        self.canvas = FigureCanvasTkAgg(self.fig, master=paned_window)
        self.canvas.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=1)

        paned_window.add(self.canvas.get_tk_widget())

        if self.datafilepath:
            self.serial_thread = threading.Thread(target=self._read_serial)
            self.serial_thread.start()
            self.root.after(int(self.update_delay_seconds*1000), self._update)
            self.root.mainloop()

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
        while not self.exit_signal.is_set():
            try:
                ser_data = self.ser.readline().decode('utf-8').strip()
                if ser_data:
                    with self.lock:
                        self.serial_data_packet = ser_data
                        self.serial_connected = True
                    with open(self.rawserialpath, "a", encoding='utf8') as f:
                        f.write(f"{ser_data}\n")
            except (serial.SerialException, AttributeError):
                with self.lock:
                    self.serial_connected = False
                while not self.serial_connected:
                    try:
                        self.ser.close()
                        self.ser = serial.Serial(self.port, self.baud_rate)
                        with self.lock:
                            self.serial_connected = True
                    except (serial.SerialException, AttributeError):
                        pass

    def _parse_serial_data(self, serial_data, delimiter="~~~"):
        try:
            data, setpoints, log = serial_data.split(delimiter, 2)
            parsed_data = ast.literal_eval(data)
            parsed_data = {int(k):float(v) for k,v in parsed_data.items()}
            parsed_setpoints = ast.literal_eval(setpoints)
            return parsed_data, parsed_setpoints, log
        except (ValueError, SyntaxError):
            return None, None, None

    def _save_files(self):
        time_seconds = time.time()
        current_time = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(time_seconds))
        self.log.append(f'Saved data at {current_time}')

        data = {'Time':self.time_data}
        for k,v in self.mc_data_dict.items():
            data[v] = self.data_channels[k]
        df = pd.DataFrame(data)

        df.to_csv(self.datafilepath, index=False)
        with open(self.logfilepath, 'w', encoding='utf8') as f:
            for entry in self.log:
                f.write(f"{entry}\n")
        self.last_save_time = time_seconds

    def _update(self):
        try:
            with self.lock:
                ser_data = self.serial_data_packet
            ser_data, esp32_setpoints, ser_log = self._parse_serial_data(ser_data)

            for k in self.mc_data_dict.keys():
                self.data_channels[k].append(ser_data[k])

            run_duration = time.time() - self.start_time
            self.time_data.append(run_duration)

            #region Plotting
            self.ax.clear()
            self.ax.set_title(self.graph_title)
            self.ax.set_xlabel('Time (s)')
            self.ax.set_ylabel(self.graph_ylabel)
            self.ax.minorticks_on()
            for k in self.mc_data_dict.keys():
                self.ax.plot(self.time_data, self.data_channels[k], label=self.mc_data_dict[k])
            self.ax.grid(True, which='major', color='silver', linewidth=0.375, linestyle='-')
            self.ax.grid(True, which='minor', color='lightgrey', linewidth=0.2, linestyle='--')
            self.fig.legend()
            self.canvas.draw()
            #endregion

            current_time = time.time()
            stringtime = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())
            if current_time - self.last_save_time >= 10:
                self._save_files()

            if self.setpoints:
                for name, entry in self.setpoint_entries.items():
                    self.setpoints[name] = float(entry.get())

            #region ESP32 setpoint check (resend if mismatched)
            matching_setpoints = True
            for k,v in self.setpoints.items():
                err = abs(esp32_setpoints[k]/v-1)
                if err > self.setpoint_check_precision:
                    matching_setpoints = False
                    self.log.append(f'Setpoint mismatch detected at {stringtime}: {k}:{v} in SimpleDAQ vs {k}:{esp32_setpoints[k]} on ESP32')
                    break

            if not matching_setpoints:
                with self.lock:
                    if self.serial_connected:
                        setpoint_json = json.dumps(self.setpoints).encode('utf-8') + b'\n'
                        self.ser.write(setpoint_json)
                        self.log.append(f'Passed new setpoints at {stringtime}: {str(setpoint_json).strip()}')
            #endregion

            #region ESP32 serial connection status
            with self.lock:
                if self.serial_connected:
                    self.status_label.config(text=f"USB Port: {self.ser.port}\nStatus: Connected", fg='green', font=("Helvetica", 12, "bold"))
                else:
                    self.status_label.config(text="USB Port: Unknown\nStatus: Disconnected", fg='red', font=("Helvetica", 12, "bold"))
                    self.log.append(f"Serial port disconnected at {stringtime}")
            if ser_log:
                self.log.append(f"{ser_log} - {stringtime}")
            #endregion

        except Exception as err:
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

class COM_Port_Dialogue(simpledialog.Dialog):
    '''Prompts user to specify COM port and baud rate.'''
    def body(self, master):
        tk.Label(master, text="COM port:").grid(row=0)
        tk.Label(master, text="Baud rate:").grid(row=1)
        self.e1 = tk.Entry(master)
        self.e2 = tk.Entry(master)
        self.e1.insert(0, "COM6")
        self.e2.insert(0, "115200")
        self.e1.grid(row=0, column=1)
        self.e2.grid(row=1, column=1)
        return self.e1

    def apply(self):
        self.result = (self.e1.get(), int(self.e2.get()))

if __name__ == '__main__':
    setpoint_dict = {'Pressure': 3}
    sdaq = SimpleDAQ({0: 'Pressure'}, setpoint_dict=setpoint_dict, update_delay_seconds=1/4)