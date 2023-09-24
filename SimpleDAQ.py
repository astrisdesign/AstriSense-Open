'''
Import-able class for communication and live plotting over USB serial.
'''
import time
import tkinter as tk
from tkinter import ttk
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
        self.datafilepath, self.logfilepath = None, None
        #endregion

        #region Prompt user for COM port
        self.root = tk.Tk()
        self.root.withdraw()  # Hide the Tkinter root window
        user_port_input = tk.simpledialog.askstring("Input", "Enter the COM port (e.g., 'COM6'):")
        self.port = user_port_input
        self.root.destroy()  # Close the Tkinter root window
        #endregion

        self.ser = serial.Serial(self.port, 115200)
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
            self.root.after(int(self.update_delay_seconds*1000), self._update)
            self.root.mainloop()
        #endregion

    def _define_save_files(self):
        self.datafilepath = tk.filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV files", "*.csv")])
        self.logfilepath = self.datafilepath.replace('.csv', '_log.txt')
        if self.datafilepath:
            self.log.append(f"Program started at {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())}")
            with open(self.logfilepath, 'w', encoding='utf8') as f:
                for entry in self.log:
                    f.write(f"{entry}\n")
            self.log.append(f"Data will be saved to {self.datafilepath}")

    def _update(self):
        try:
            ser_data = self.ser.readline().decode('utf-8').strip()
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

            # Update status label for connected state
            self.status_label.config(text=f"USB Port: {self.ser.port}\nStatus: Connected", fg='green', font=("Helvetica", 12, "bold"))

            if run_duration % 10 < 1:
                df = pd.DataFrame({"Time": self.time_data, "Pressure": self.pressure_data})
                df.to_csv(self.datafilepath, index=False)
                with open(self.logfilepath, 'w', encoding='utf8') as f:
                    for entry in self.log:
                        f.write(f"{entry}\n")

        except (serial.SerialException, AttributeError):
            # Update status label for disconnected state
            self.status_label.config(text="USB Port: Unknown\nStatus: Disconnected", fg='red', font=("Helvetica", 12, "bold"))

            self.log.append(f"Serial port error at {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())}")
            try:
                self.ser.close()
                self.ser = serial.Serial(self.ser.port, 115200)
                self.log.append(f"Reconnected to serial port {self.ser.port} at {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())}")
            except (serial.SerialException, AttributeError):
                self.log.append(f"Failed to reconnect at {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())}")

        finally:
            self.root.after(int(1000*self.update_delay_seconds), self._update)

    def _user_input(self, inputdata):
        self.log.append(f"User input at {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())}: {inputdata}")

    def _exit_program(self):
        self.log.append(f"Program exited at {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(time.time()))}")
        with open(self.logfilepath, 'w', encoding='utf8') as f:
            for entry in self.log:
                f.write(f"{entry}\n")
        self.ser.close()
        self.root.quit()
        self.root.destroy()

if __name__ == '__main__':
    sdaq = SimpleDAQ({}, 1/4)
