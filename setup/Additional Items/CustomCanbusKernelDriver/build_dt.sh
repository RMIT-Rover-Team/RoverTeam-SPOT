dtc -@ -I dts -O dtb -o mcpcustom.dtbo mcpcustom.dts 
sudo cp mcpcustom.dtbo /boot/firmware/overlays/

#Add to /boot/config
# dtoverlay=mcp2517fd-20mhz-noirq

