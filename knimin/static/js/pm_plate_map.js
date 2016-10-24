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
  var scope = this;
  $.get('/pm_plate_map/info/', {id: this.id})
    .done(function(data) {
      var info = JSON.parse(data);
      if (!('name' in info)) throw 'Invalid data structure.';
      scope.name = info['name'];
      var html = '<p>Plate #' + id.toString() + ': ' + info['name'] + '</p>';
      $('.content').append(html);
    })
    .fail(function() {
      console.log('The AJAX call failed');
    });
};

/**
 * Display an interactive name box.
 * @this {plateMap}
 */
plateMap.prototype.nameBox = function() {
  var scope = this;
  $.get('/pm_plate_map/info/', {id: this.id})
    .done(function(data) {
      var info = JSON.parse(data);
      scope.name = info['name'];
      if (!('name' in info)) throw 'Invalid plate information.';
      $('.content').append($('<p/>').attr('id', 'title-bar'));
      $('#title-bar').append($('<label/>').attr({'id': 'plate-id'})
        .text('Plate # ' + id.toString() + ': '));
      $('#title-bar').append($('<input/>').attr({'id': 'plate-name', 'type':
        'text', 'style': 'width:200px'}).val(info['name']));
      $(document).on('focus', '#plate-name', function() {
        $(this).select();
      });
      $('#title-bar').append(' ');
      $('#title-bar').append($('<button/>').attr({'id': 'btn-save'})
        .text('Save'));
      // $(document).on('click', '#btn-save', scope.saveInfo);
      $(document).on('click', '#btn-save', function() {
        scope.saveInfo(scope);
      });
    });
};

/**
 * Alert plate name
 * @param {plateMap} pm
 */
plateMap.prototype.saveInfo = function(pm) {
  alert(pm.name);
  // alert($(this).text());
};
