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
    def __init__(self, mc_data_dict, setpoint_dict=None, update_delay_seconds=1, graph_title='', graph_ylabel='Sensor Data', setpoint_decimals=3, setpoint_check_precision=.001):
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
        self.window_size = 200  # Default window "size" (number of observations) for the graph
        self.setpoints = setpoint_dict
        self.setpoint_decimals = setpoint_decimals
        self.setpoint_check_precision = setpoint_check_precision
        self.default_COM_port = 'COM6'
        self.default_baud_rate = 115200
        self.toggle_keys = None
        if setpoint_dict:
            self._setpoint_mapping = {k: i for i, k in enumerate(setpoint_dict.keys())}
        else:
            self._setpoint_mapping = {}
            self.setpoints = {}

    def start_gui(self):
        self.root = tk.Tk()
        self.root.withdraw()
        d = COM_Port_Dialogue(self.root, self.default_COM_port, self.default_baud_rate)
        self.port, self.baud_rate = d.result
        self.root.destroy()
        self.ser = serial.Serial(self.port, self.baud_rate)
        self._define_save_files()

        self.root = tk.Tk()
        self.root.title("Data Logging GUI")

        paned_window = tk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        paned_window.pack(fill=tk.BOTH, expand=1)
        control_frame = tk.Frame(paned_window, width=200, height=400, bg='lightgrey')
        control_frame.pack_propagate(False)

        ttk.Button(control_frame, text="Exit", command=self._exit_program).pack(side=tk.TOP, pady=10)
        self.status_label = tk.Label(control_frame, text="Status: Connected", bg='lightgrey')
        self.status_label.pack(side=tk.TOP, pady=10)

        # Create a frame for window size label and entry
        window_size_frame = tk.Frame(control_frame)
        window_size_frame.pack(side=tk.TOP, padx=10, pady=10)
        self.window_size_label = tk.Label(window_size_frame, text="Window Size:")
        self.window_size_label.grid(row=0, column=0)
        self.window_size_entry = tk.Entry(window_size_frame)
        self.window_size_entry.insert(0, str(self.window_size))
        self.window_size_entry.grid(row=0, column=1)

        paned_window.add(control_frame)

        setpoint_frame = tk.Frame(control_frame)
        setpoint_frame.pack(side=tk.TOP, padx=10, pady=10)
        tk.Label(setpoint_frame, text="Setpoints").pack()

        if self.setpoints:
            self.setpoint_entries = {}
            for name, value in self.setpoints.items():
                frame = tk.Frame(setpoint_frame)
                frame.pack(side=tk.TOP, padx=5, pady=5, fill=tk.X, expand=True)
                tk.Label(frame, text=name).pack(side=tk.LEFT)
                entry = tk.Entry(frame)
                entry.insert(0, str(value))
                entry.pack(side=tk.RIGHT)
                self.setpoint_entries[name] = entry
        if self.toggle_keys:
            self.create_toggle_buttons(self.toggle_keys)

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
    
    def create_toggle_buttons(self, toggle_keys):
        """
        Creates toggle buttons for specified setpoints.
        Args:
            toggle_keys (list): Keys of the setpoints to be converted into toggle buttons.
        """
        for key in toggle_keys:
            if key in self.setpoint_entries:
                entry = self.setpoint_entries.pop(key)
                entry.pack_forget()  # Remove the existing entry widget

                # Determine toggle button state (text and color)
                initial_value = self.setpoints.get(key, 0)
                if initial_value == 1:
                    button_text, button_color = 'ON', '#00FF00'
                elif initial_value == 0:
                    button_text, button_color = 'OFF', 'darkgrey'
                else:
                    raise ValueError('Toggle setpoints must have initial values of 0 (off) or 1 (on).')

                toggle_button = tk.Button(entry.master, text=button_text, bg=button_color, command=lambda k=key: self.toggle_setpoint(k))
                toggle_button.pack(side=tk.RIGHT, anchor='e')
                self.setpoint_entries[key] = {'button': toggle_button, 'value': initial_value}  # Store button and value separately

    def toggle_setpoint(self, key):
        """
        Toggles the setpoint value and updates the button appearance.
        Args:
            key (str): The key of the setpoint to toggle.
        """
        self.setpoint_entries[key]['value'] = 1 - self.setpoint_entries[key]['value']  # Toggle between 0 and 1
        button = self.setpoint_entries[key]['button']
        if self.setpoint_entries[key]['value']:
            button.config(bg='#00FF00', text='ON')  # Green background and 'ON' if value = 1
        else:
            button.config(bg='darkgrey', text='OFF')  # Grey background and 'OFF' if value = 0

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
            parsed_data = {int(k): float(v) for k, v in parsed_data.items()}
            parsed_setpoints = ast.literal_eval(setpoints)
            return parsed_data, parsed_setpoints, log

        except Exception as e:
            error_text = f'Unexpected Error: {e}'
            return None, None, error_text

    def _send_setpoints(self):
        # Translate setpoint names to their integer mappings
        integer_setpoints = {self._setpoint_mapping[k]: v for k, v in self.setpoints.items()}
        setpoint_json = json.dumps(integer_setpoints).encode('utf-8') + b'\n'
        self.ser.write(setpoint_json)
        return setpoint_json  # Return the JSON string for logging

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

    def _update(self): # NEW
        try:
            with self.lock:
                ser_data = self.serial_data_packet
            ser_data, esp32_setpoints, ser_log = self._parse_serial_data(ser_data)

            # Process the serial data
            for k in self.mc_data_dict.keys():
                self.data_channels[k].append(ser_data[k])

            run_duration = time.time() - self.start_time
            self.time_data.append(run_duration)

            #region Plotting
            try:
                self.window_size = int(self.window_size_entry.get())
            except ValueError:
                self.window_size = 200  # Default to 200 if invalid input
            start_idx = max(0, len(self.time_data) - self.window_size)

            self.ax.clear()
            self.ax.set_title(self.graph_title)
            self.ax.set_xlabel('Time (s)')
            self.ax.set_ylabel(self.graph_ylabel)
            self.ax.minorticks_on()
            for k in self.mc_data_dict.keys():
                self.ax.plot(self.time_data[start_idx:], self.data_channels[k][start_idx:], label=self.mc_data_dict[k])
            self.ax.grid(True, which='major', color='silver', linewidth=0.375, linestyle='-')
            self.ax.grid(True, which='minor', color='lightgrey', linewidth=0.2, linestyle='--')
            self.ax.legend(fontsize='small')
            self.canvas.draw()
            #endregion

            current_time = time.time()
            stringtime = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())
            if current_time - self.last_save_time >= 10:
                self._save_files()

            # Update setpoints from the GUI entries
            if self.setpoints:
                for name, entry in self.setpoint_entries.items():
                    try:
                        self.setpoints[name] = round(float(entry.get()), self.setpoint_decimals)
                    except TypeError: # Toggle buttons don't have .get
                        self.setpoints[name] = entry['value']
                    except ValueError:
                        pass

            #region ESP32 setpoint check (resend if mismatched)
            matching_setpoints = True
            for k, v in self.setpoints.items():
                mapped_index = self._setpoint_mapping[k]
                esp32_value = esp32_setpoints[str(mapped_index)]
                if esp32_value is None:
                    continue

                if isinstance(v, str):
                    err = 0  # Ignore string inputs
                elif v > .000001:
                    err = abs(esp32_value / v - 1)
                else:
                    err = abs(esp32_value - v)  # Use absolute error for very low values

                if err > self.setpoint_check_precision:
                    matching_setpoints = False
                    self.log.append(f'Setpoint mismatch detected at {stringtime}: {k} [{self._setpoint_mapping[k]}]:{v} in SimpleDAQ vs {mapped_index}:{esp32_value} on ESP32')
                    break

            if not matching_setpoints:
                with self.lock:
                    if self.serial_connected:
                        setpoint_json = self._send_setpoints()  # Send setpoints over USB serial and capture the JSON
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
            self.log.append(f"Unhandled error: {err}. Serial log: {str(ser_log)}")

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
    def __init__(self, master, default_COM_port="COM6", default_baud_rate="115200"):
        self.default_COM_port = default_COM_port
        self.default_baud_rate = default_baud_rate
        super().__init__(master)

    def body(self, master):
        tk.Label(master, text="COM port:").grid(row=0)
        tk.Label(master, text="Baud rate:").grid(row=1)
        self.e1 = tk.Entry(master)
        self.e2 = tk.Entry(master)
        self.e1.insert(0, self.default_COM_port)
        self.e2.insert(0, str(self.default_baud_rate))
        self.e1.grid(row=0, column=1)
        self.e2.grid(row=1, column=1)
        return self.e1

    def apply(self):
        self.result = (self.e1.get(), int(self.e2.get()))

if __name__ == '__main__':
    setpoint_dict = {'Pressure': -1}
    sdaq = SimpleDAQ({0: 'Pressure'}, setpoint_dict=setpoint_dict, update_delay_seconds=1/4)