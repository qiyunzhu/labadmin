/** Master object controlling all Plate Mapper operations */

/**
 * Initiate the webpage
 * @this {plateMap}
 * @param {integer} id
 *  ID of plate
 * @param {string} target
 *  Category of plate (default: sample)
 */
var plateMap = function(id, target) {
  this.id = id;
  if (target === undefined) {
    target = 'sample';
  }
  this.target = target;
};

/**
 * Print ID to page.
 * @this {plateMap}
 */
plateMap.prototype.printID = function() {
  // $('.content').append('<p>' + this.id + '</p>');
  $.get('/pm_plate_map/info/', {id: this.id})
    .done(function(data) {
      var info = JSON.parse(data);
      if (!('name' in info)) throw 'Invalid data structure.';
      var html = '<p>Plate #' + id.toString() + ': ' + info['name'] + '</p>';
      $('.content').append(html);
    });
};
