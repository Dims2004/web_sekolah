// Camera utility functions
class CameraUtils {
    static async getCameraList() {
        try {
            const devices = await navigator.mediaDevices.enumerateDevices();
            return devices.filter(device => device.kind === 'videoinput');
        } catch (error) {
            console.error('Error getting camera list:', error);
            return [];
        }
    }
    
    static async switchCamera(deviceId) {
        try {
            const stream = await navigator.mediaDevices.getUserMedia({
                video: { deviceId: { exact: deviceId } }
            });
            return stream;
        } catch (error) {
            console.error('Error switching camera:', error);
            return null;
        }
    }
}