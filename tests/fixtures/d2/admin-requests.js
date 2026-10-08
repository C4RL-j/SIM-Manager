/* Synthetic scaffolding around observed firmware request descriptors and
 * view property names. No runtime response, successful authentication,
 * actual credential, identifier, or field value is represented here.
 */
function syntheticReadDescriptors() {
  return [
    {url: "/web/v1/dashboard/wirelessinfo", method: "get"},
    {url: "/web/v1/dashboard/internetinfo", method: "get"},
    {url: "/web/v1/dashboard/waninfo", method: "get"},
    {url: "/web/v1/dashboard/deviceinfo", method: "get"},
    {url: "/web/v1/status/wanstatus", method: "get"},
    {url: "/web/v1/setting/network/pinmanagement/simcardinfo", method: "get"},
    {url: "/web/v1/setting/deviceinfo", method: "get"}
  ];
}

function syntheticViewBindings(view) {
  return [
    view.RSRP0, view.RSRP1, view.UICCID, view.USIMStatus, view.SIMCardState,
    view.RetriesPIN, view.PINCheckEnabled, view.ECellId, view.ConnectStatus,
    view.ConnectMode, view.ConnectionStatus, view.DeviceModel, view.ProductModel,
    view.HardwareVersion, view.SoftwareVersion, view.RouterVersion,
    view.RunningTime, view.UBootVersion, view.SerialNumber, view.IpAddress,
    view.SubnetMask, view.MacAddress, view.IMEI
  ];
}
